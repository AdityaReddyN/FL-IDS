"""Smoke test for the generation throughput benchmark (S7a)."""

import importlib.util
from pathlib import Path

import pandas as pd

from flids.attacks.assembler import OverlaySpec

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("benchmark_generation", ROOT / "scripts" / "benchmark_generation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frame():
    rows = []
    for aircraft in ("a00001", "a00002", "a00003"):
        for offset in range(100):
            rows.append({
                "icao24": aircraft, "segment_id": 0, "time": offset * 10,
                "lat": 30.0 + offset * 0.001, "lon": 10.0 + offset * 0.001,
                "velocity": 220.0, "heading": 90.0, "vertrate": 1.0,
                "baroaltitude": 3000.0 + offset, "geoaltitude": 3010.0 + offset,
                "onground": False, "contact_lag_seconds": 0.0, "contact_lag_missing": False,
                **{f"{f}_missing": False for f in ("lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude")},
            })
    return pd.DataFrame(rows)


def test_benchmark_reports_throughput():
    module = _load()
    overlay = OverlaySpec("constant_deviation", "moderate", subtype="constant",
                          duration_seconds=100, magnitude_m=5000.0, tau=1.0)
    result = module.benchmark(_frame(), [overlay], 7, lambda ic: "train")
    assert result["rows"] == 300 and result["segments"] == 3
    assert result["rows_per_second"] and result["rows_per_second"] > 0
    assert result["accepted_episodes"] >= 1
