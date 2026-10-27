"""Tests for the deterministic aircraft-hash working subset (S7)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("make_working_subset", ROOT / "scripts" / "make_working_subset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sampled_is_deterministic_and_fraction_scales():
    m = _load()
    ids = [f"a{i:05d}" for i in range(4000)]
    at10 = {i for i in ids if m.sampled(i, 42, 0.10)}
    at10_again = {i for i in ids if m.sampled(i, 42, 0.10)}
    at25 = {i for i in ids if m.sampled(i, 42, 0.25)}
    assert at10 == at10_again                       # deterministic
    assert at10 <= at25                             # nested as fraction grows
    assert 0.07 < len(at10) / len(ids) < 0.13       # ~10%


def test_build_subset_writes_sorted_parquet_and_manifest(tmp_path):
    m = _load()
    clean = tmp_path / "clean"
    clean.mkdir()
    rows = []
    for a in range(40):
        icao = f"{a:06x}"
        for i in range(20):
            rows.append({"icao24": icao, "segment_id": 0, "time": i * 10,
                         "lat": 10.0 + a, "lon": 20.0 + a})
    df = pd.DataFrame(rows)
    df.to_parquet(clean / "part_0000.parquet", index=False)
    split = {"train": [f"{a:06x}" for a in range(28)],
             "val": [f"{a:06x}" for a in range(28, 34)],
             "test": [f"{a:06x}" for a in range(34, 40)]}
    (clean / "split_aircraft.json").write_text(json.dumps(split), encoding="utf-8")

    out = tmp_path / "subset.parquet"
    manifest = m.build_subset(clean, out, fraction=0.5, seed=42)
    assert out.exists()
    sub = pd.read_parquet(out)
    # Sorted by (icao24, segment_id, time) so file order == source_row_id order.
    assert sub[["icao24", "segment_id", "time"]].equals(
        sub.sort_values(["icao24", "segment_id", "time"]).reset_index(drop=True)[["icao24", "segment_id", "time"]])
    assert manifest["aircraft"] == sub["icao24"].nunique()
    assert manifest["content_fingerprint"]
    assert (out.with_suffix(".manifest.json")).exists()
