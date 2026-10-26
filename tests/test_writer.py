"""Tests for the guarded, chunked Stage 1 Parquet writer."""

import hashlib
import json

import pandas as pd
import pytest

from flids.attacks import writer
from flids.attacks.assembler import OverlaySpec
from flids.attacks.schemas import validate_table


def source_frame():
    rows = []
    for aircraft, split in (("a00001", "train"), ("a00002", "val"), ("a00003", "test")):
        for offset in range(100):
            rows.append({
                "icao24": aircraft, "segment_id": 0, "time": offset * 10,
                "lat": 30.0 + offset * .001, "lon": 10.0 + offset * .001,
                "velocity": 200.0, "heading": 90.0, "vertrate": 1.0,
                "baroaltitude": 3000.0 + offset, "geoaltitude": 3010.0 + offset,
                "onground": False, "contact_lag_seconds": 0.0,
                "contact_lag_missing": False,
                **{f"{field}_missing": False for field in ("lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude")},
            })
    return pd.DataFrame(rows)


def split_of(icao24):
    return {"a00001": "train", "a00002": "val", "a00003": "test"}[icao24]


def overlay():
    return OverlaySpec("constant_deviation", "moderate", subtype="constant", duration_seconds=100, magnitude_m=5000.0, tau=0.0)


def invoke(tmp_path, config, monkeypatch, dirty=False, overlay_specs=None, resolved_plan=None):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("status: approved\n", encoding="utf-8")
    monkeypatch.setattr(writer, "git_dirty", lambda _root: dirty)
    return writer.write_overlay_tables(
        source_frame(), overlay() if overlay_specs is None else overlay_specs, 17, split_of, config,
        config_path=config_path, output_dir=tmp_path / "new-run",
        resolved_plan=resolved_plan,
        max_segments_per_chunk=1,
    )


def test_writer_refuses_unapproved_config(tmp_path, monkeypatch):
    with pytest.raises(writer.WriterError, match="approved"):
        invoke(tmp_path, {"status": "proposed_unapproved"}, monkeypatch)


def test_writer_refuses_dirty_tree(tmp_path, monkeypatch):
    with pytest.raises(writer.WriterError, match="dirty"):
        invoke(tmp_path, {"status": "approved"}, monkeypatch, dirty=True)


def test_writer_refuses_existing_output(tmp_path, monkeypatch):
    output = tmp_path / "new-run"
    output.mkdir()
    with pytest.raises(writer.WriterError, match="overwrite"):
        invoke(tmp_path, {"status": "approved"}, monkeypatch)


def test_writer_streams_schema_validated_tables_and_manifest(tmp_path, monkeypatch):
    manifest = invoke(tmp_path, {"status": "approved"}, monkeypatch)
    output = tmp_path / "new-run"
    assert manifest["git_dirty"] is False
    assert manifest["overlay_merge_order"] == [overlay().overlay_key]
    assert manifest["overlay_merge_scope"].startswith("lexicographic_overlay_key")
    assert set(manifest["tables"]) == {
        "attacked_rows", "step_labels", "episodes", "rejected_candidates",
        "modified_row_provenance", "windows", "segments", "overlay_selections",
    }
    for name, details in manifest["tables"].items():
        path = output / f"{name}.parquet"
        loaded = pd.read_parquet(path)
        assert details["row_count"] == len(loaded)
        validate_table(loaded, name)
        assert details["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert manifest["validator_results"][name] == "passed"
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8")) == manifest
    run_config = json.loads((output / "config.json").read_text(encoding="utf-8"))
    assert run_config["global_seed"] == 17
    assert run_config["overlay_specs"][0]["overlay_key"] == overlay().overlay_key
    assert "python" in run_config["library_versions"]
    report = json.loads((output / "plausibility_report.json").read_text(encoding="utf-8"))
    assert report["episode_count"] == 0
    assert report["unavailable_checks"]


def test_writer_records_multi_overlay_merge_order_and_selection(tmp_path, monkeypatch):
    constant = OverlaySpec("constant_deviation", "moderate", subtype="constant", duration_seconds=100, magnitude_m=5000.0, tau=1.0)
    gaussian = OverlaySpec("random_gaussian_deviation", "moderate", subtype="gaussian", duration_seconds=100, sigma_m=500.0, tau=1.0)
    plan = [{"family": "random_gaussian_deviation", "tier": "moderate", "duration_seconds": 100, "tau": 1.0},
            {"family": "constant_deviation", "tier": "moderate", "duration_seconds": 100, "tau": 1.0}]
    manifest = invoke(tmp_path, {"status": "approved"}, monkeypatch, overlay_specs=[gaussian, constant], resolved_plan=plan)
    assert manifest["overlay_merge_order"] == sorted([constant.overlay_key, gaussian.overlay_key])
    assert set(manifest["overlays"]) == {constant.overlay_key, gaussian.overlay_key}
    assert manifest["tables"]["overlay_selections"]["row_count"] == 6
    assert manifest["merged_totals"]["rejected_by_reason"]["overlay_conflict"] > 0
    # S1.5 manifest additions.
    assert manifest["resolved_plan"] == plan
    assert manifest["total_elapsed_seconds"] >= 0.0
    assert manifest["chunk_seconds_summary"]["n_chunks"] == 3
    assert isinstance(manifest["window_counts_by_label_stratum_family_split"], dict)
    constant_overlay = manifest["overlays"][constant.overlay_key]
    assert constant_overlay["unique_aircraft"] >= 1
    assert constant_overlay["window_count"] >= 0
    assert set(constant_overlay["tau_by_split"]).issubset({"train", "val", "test"})
    for split_stats in constant_overlay["tau_by_split"].values():
        assert split_stats["tau_requested"] == 1.0


def test_writer_reports_chunk_progress_without_changing_output(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("status: approved\\n", encoding="utf-8")
    monkeypatch.setattr(writer, "git_dirty", lambda _root: False)
    updates = []
    manifest = writer.write_overlay_tables(
        source_frame(), overlay(), 17, split_of, {"status": "approved"},
        config_path=config_path, output_dir=tmp_path / "progress-run",
        max_segments_per_chunk=1, progress_callback=updates.append,
    )
    starts = [item for item in updates if item["event"] == "chunk_start"]
    completes = [item for item in updates if item["event"] == "chunk_complete"]
    assert [item["chunk_index"] for item in starts] == [1, 2, 3]
    assert [item["chunk_index"] for item in completes] == [1, 2, 3]
    assert [item["segments_processed"] for item in completes] == [1, 2, 3]
    assert all(item["elapsed_seconds"] >= 0 for item in updates)
    assert all(item["chunk_seconds"] >= 0 for item in completes)
    assert all(item["rows_written"]["attacked_rows"] == 100 * i for i, item in enumerate(completes, 1))
    assert manifest["tables"]["attacked_rows"]["row_count"] == 300
