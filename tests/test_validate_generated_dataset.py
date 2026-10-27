"""Fixture test for scripts/validate_generated_dataset.py (S7a)."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flids.attacks import writer
from flids.attacks.assembler import OverlaySpec

ROOT = Path(__file__).resolve().parents[1]


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_generated_dataset", ROOT / "scripts" / "validate_generated_dataset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_frame() -> pd.DataFrame:
    rows = []
    for aircraft in ("a00001", "a00002", "a00003"):
        for offset in range(120):
            rows.append({
                "icao24": aircraft, "segment_id": 0, "time": offset * 10,
                "lat": 30.0 + offset * 0.001, "lon": 10.0 + offset * 0.001,
                "velocity": 220.0, "heading": 90.0, "vertrate": 1.0,
                "baroaltitude": 3000.0 + offset, "geoaltitude": 3010.0 + offset,
                "onground": False, "contact_lag_seconds": 0.0, "contact_lag_missing": False,
                **{f"{f}_missing": False for f in ("lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude")},
            })
    return pd.DataFrame(rows)


def split_of(icao):
    return {"a00001": "train", "a00002": "val", "a00003": "test"}[icao]


def _write_run(tmp_path, monkeypatch):
    frame = _source_frame()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("status: approved\n", encoding="utf-8")
    monkeypatch.setattr(writer, "git_dirty", lambda _root: False)
    overlay = OverlaySpec("constant_deviation", "moderate", subtype="constant",
                          duration_seconds=120, magnitude_m=5000.0, tau=1.0)
    run_dir = tmp_path / "run"
    writer.write_overlay_tables(frame, overlay, 7, split_of, {"status": "approved"},
                                config_path=config_path, output_dir=run_dir, max_segments_per_chunk=8)
    source_path = tmp_path / "source.parquet"
    frame.to_parquet(source_path, index=False)
    return run_dir, source_path, frame


def test_validator_passes_on_a_clean_run(tmp_path, monkeypatch):
    validator = _load_validator()
    run_dir, source_path, _ = _write_run(tmp_path, monkeypatch)
    report = validator.validate(run_dir, source_path)
    assert report["passed"], {k: v for k, v in report["checks"].items() if not v["passed"]}
    # Spot-check the semantic checks actually ran.
    assert report["checks"]["source_one_to_one_and_unchanged"]["passed"]
    assert report["checks"]["ramp_effect_and_injection"]["passed"]
    assert report["checks"]["windows_recomputed"]["passed"]


def test_validator_detects_tampered_source_values(tmp_path, monkeypatch):
    validator = _load_validator()
    run_dir, source_path, frame = _write_run(tmp_path, monkeypatch)
    # Corrupt the source so orig_* no longer matches.
    frame.loc[0, "lat"] = frame.loc[0, "lat"] + 10.0
    frame.to_parquet(source_path, index=False)
    report = validator.validate(run_dir, source_path)
    assert not report["passed"]
    assert not report["checks"]["source_one_to_one_and_unchanged"]["passed"]
