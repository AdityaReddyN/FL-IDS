import numpy as np

from flids.attacks.assembler import OverlaySpec, assemble_overlay
from flids.attacks.plausibility import build_plausibility_report


def source():
    rows = []
    for aircraft in ("a00001", "a00002", "a00003"):
        for i in range(100):
            row = {
                "icao24": aircraft, "segment_id": 0, "time": i * 10,
                "lat": 30 + i * .001, "lon": 10 + i * .001,
                "velocity": 20.0, "heading": 90.0, "vertrate": 1.0,
                "baroaltitude": 1000.0 + i * 10, "geoaltitude": 1010.0 + i * 10,
                "onground": False, "contact_lag_seconds": 0.0,
                "contact_lag_missing": False,
            }
            row.update({f"{field}_missing": False for field in ("lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude")})
            rows.append(row)
    import pandas as pd
    return pd.DataFrame(rows)


def test_plausibility_report_has_episode_kinematics_missingness_and_limits():
    assembled = assemble_overlay(
        source(),
        OverlaySpec("constant_deviation", "moderate", subtype="constant", duration_seconds=100, magnitude_m=5000, tau=1.0),
        5,
        lambda _icao24: "train",
    )
    report = build_plausibility_report(assembled.attacked_rows, assembled.episodes, assembled.rejected_candidates)
    assert report["episode_count"] == len(assembled.episodes)
    assert report["episodes"]
    item = report["episodes"][0]
    assert "implied_ground_speed_mps" in item["kinematics"]
    assert "turn_rate_deg_per_s" in item["kinematics"]
    assert "baro_vertical_rate_mps" in item["kinematics"]
    assert set(item["kinematics"]["continuity_distance_m_by_phase"]) == {"before", "during", "after"}
    assert set(item["missing_fraction"]) == {"before", "during", "after"}
    assert "RF replay fidelity" in report["unavailable_checks"]
    assert report["threshold_validation"] == "descriptive_only_no_cutoffs_approved"


def test_plausibility_report_uses_null_for_unavailable_metrics():
    import pandas as pd
    rows = pd.DataFrame(columns=["icao24", "segment_id", "time"])
    report = build_plausibility_report(rows, pd.DataFrame(), pd.DataFrame())
    assert report["episode_count"] == 0
    assert report["episodes"] == []
