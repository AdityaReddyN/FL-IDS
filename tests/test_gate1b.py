"""Mini end-to-end test for scripts/gate1b_calibration.py (S6)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from flids.data.clean import clean_frame

ROOT = Path(__file__).resolve().parents[1]


def _load_gate1b():
    spec = importlib.util.spec_from_file_location("gate1b_calibration", ROOT / "scripts" / "gate1b_calibration.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _aircraft_rows(icao: str, velocity: float, n: int, rng) -> list[dict]:
    rows = []
    lat = 10.0
    for i in range(n):
        # Consistent due-north motion at `velocity`, plus a few metres of noise
        # so residuals are non-degenerate (positive p95 threshold, ~5% FPR).
        step = velocity * 10.0 / 111_320.0
        lat += step + rng.normal(0, 3.0) / 111_320.0
        rows.append({
            "time": i * 10, "icao24": icao, "lat": lat, "lon": 20.0,
            "velocity": velocity, "heading": 0.0, "vertrate": 0.0,
            "baroaltitude": 3000.0 + i, "geoaltitude": 3010.0 + i,
            "onground": False, "lastcontact": i * 10,
        })
    return rows


def _make_clean_dir(tmp_path: Path) -> Path:
    rng = np.random.default_rng(0)
    rows = []
    for icao, vel in (("aaaaaa", 150.0), ("bbbbbb", 250.0), ("cccccc", 30.0), ("dddddd", 160.0)):
        rows += _aircraft_rows(icao, vel, 60, rng)
    clean = clean_frame(pd.DataFrame(rows))
    out = tmp_path / "hdd_clean_v1"
    out.mkdir()
    clean.to_parquet(out / "part_0000.parquet", index=False)
    split = {"train": ["aaaaaa", "bbbbbb", "dddddd"], "val": ["cccccc"], "test": []}
    (out / "split_aircraft.json").write_text(json.dumps(split), encoding="utf-8")
    return out


def test_gate1b_end_to_end_produces_thresholds_recall_and_capacity(tmp_path):
    gate1b = _load_gate1b()
    clean_dir = _make_clean_dir(tmp_path)
    report = gate1b.run(clean_dir, reservoir=100_000, seed=42)

    thr = report["speed_band_train_p95_threshold_m"]
    assert thr["100_200"] is not None and thr["100_200"] >= 0.0

    manip = report["manipulation_recall_by_magnitude"]
    assert set(manip) == {"abrupt", "real_ramp"}
    # Large magnitude in a fast band is detected; abrupt >= ramp.
    assert manip["abrupt"]["100_200"]["16000"] == 1.0
    assert manip["abrupt"]["100_200"]["16000"] >= manip["real_ramp"]["100_200"]["16000"]

    # Tier proposal exists for a fast band and is monotone non-decreasing.
    tiers = report["tier_proposal_fast_bands_abrupt"]["100_200"]
    vals = [tiers[k] for k in ("recall_10pct", "recall_30pct", "recall_60pct", "recall_90pct") if tiers[k] is not None]
    assert vals == sorted(vals)

    # FPR near the 5% construction target for the train bands.
    for band, value in report["oracle_fpr_on_matched_controls"].items():
        assert 0.0 <= value <= 0.25

    # Capacity: nominal-120s episodes have train starts (60-row tracks).
    cap = report["per_overlay_capacity_by_split_speed_band"]["nominal_120s"]["train"]
    assert any(cell["episode_starts"] > 0 for cell in cap.values())
    assert "altitude_oracle" in report and "partial_replay_recall" in report
