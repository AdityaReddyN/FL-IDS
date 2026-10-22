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


def invoke(tmp_path, config, monkeypatch, dirty=False):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("status: approved\n", encoding="utf-8")
    monkeypatch.setattr(writer, "git_dirty", lambda _root: dirty)
    return writer.write_overlay_tables(
        source_frame(), overlay(), 17, split_of, config,
        config_path=config_path, output_dir=tmp_path / "new-run",
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
    assert manifest["overlay_merge_scope"].startswith("single_overlay_per_run")
    assert set(manifest["tables"]) == {
        "attacked_rows", "step_labels", "episodes", "rejected_candidates",
        "modified_row_provenance", "windows", "segments",
    }
    for name, details in manifest["tables"].items():
        path = output / f"{name}.parquet"
        loaded = pd.read_parquet(path)
        assert details["row_count"] == len(loaded)
        validate_table(loaded, name)
        assert details["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert manifest["validator_results"][name] == "passed"
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8")) == manifest
    report = json.loads((output / "plausibility_report.json").read_text(encoding="utf-8"))
    assert report["episode_count"] == 0
    assert report["unavailable_checks"]
