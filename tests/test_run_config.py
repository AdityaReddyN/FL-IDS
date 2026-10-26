import pytest

from flids.attacks.run_config import (
    dry_run_summary, overlay_from_config, overlays_from_plan, plan_mode, quota_targets_from_plan,
)


def config():
    return {
        "episodes": {"nominal_duration_seconds": 120, "max_per_segment": 3, "minimum_inter_episode_gap_seconds": 600, "freeze_duration_tiers_seconds": {"moderate": 120}, "onset": {"default_steps": 3}},
        "attacks": {"stage1_types": ["constant_deviation", "random_gaussian_deviation", "gradual_deviation", "altitude_constant_deviation", "replay_partial_field", "replay_full_field", "freeze_fixed_value"], "altitude_variants": ["baro_only", "baro_plus_geo"], "gaussian": {"deviation_sigma_meters_by_tier": {"moderate": 1250.0}, "eq12_noise_kappa_by_tier": {"moderate": 0.1}, "per_step_noise_sigma_meters": 25.0}},
        "tiers": {"horizontal_meters": {"moderate": 2500.0}, "altitude_residual_calibration_meters": {"shared_shift_both_variants": {"moderate": 125.0}}},
        "region": {"primary_dataset_mode": "uniform_per_subairspace"},
        "prevalence": {"tau_sweep": [0.005, 0.01]},
        "eligibility": {"replay": {"paper_grounded_delay_seconds": 300, "timestamp_tolerance_seconds": 5}, "geoaltitude_glitch_screen": {"train_only_q999_threshold_meters": 2887.98}},
    }


def test_overlay_from_config_maps_family_parameters_without_yaml_io():
    cfg = config()
    constant = overlay_from_config(cfg, "constant_deviation", "moderate")
    assert constant.magnitude_m == 2500.0
    assert constant.tau == 0.005
    gaussian = overlay_from_config(cfg, "random_gaussian_deviation", "moderate")
    assert gaussian.sigma_m == 1250.0
    assert gaussian.kappa == 0.1
    altitude = overlay_from_config(cfg, "altitude_constant_deviation", "moderate", altitude_variant="baro_plus_geo")
    assert altitude.shift_m == 125.0
    assert altitude.geoaltitude_glitch_threshold_m == 2887.98
    replay = overlay_from_config(cfg, "replay_partial_field", "moderate")
    assert replay.replay_delay_s == 300


def test_overlay_from_config_rejects_out_of_config_choices():
    with pytest.raises(ValueError, match="unsupported attack family"):
        overlay_from_config(config(), "ghost_injection", "moderate")
    with pytest.raises(ValueError, match="tier"):
        overlay_from_config(config(), "constant_deviation", "gross")


def test_overlay_from_config_plumbs_onset_mode():
    overlay = overlay_from_config(config(), "constant_deviation", "moderate", onset_mode="abrupt")
    assert overlay.onset_mode == "abrupt"


def test_overlays_from_plan_builds_tau_overlays_with_onset_mode():
    plan = {
        "plan_version": 1,
        "overlays": [
            {"family": "constant_deviation", "tier": "moderate", "duration_seconds": 120, "tau": 0.005},
            {"family": "gradual_deviation", "tier": "moderate", "duration_seconds": 900,
             "onset_mode": "abrupt", "tau": 0.01},
        ],
    }
    overlays = overlays_from_plan(config(), plan)
    assert [o.attack_family for o in overlays] == ["constant_deviation", "gradual_deviation"]
    assert overlays[0].onset_mode == "linear_mix" and overlays[0].tau == 0.005
    assert overlays[1].onset_mode == "abrupt" and overlays[1].duration_seconds == 900


def test_quota_plan_builds_overlays_and_targets():
    cfg = config()
    cfg["quota_mode"] = {
        "target_episodes_per_cell": {"train": 300, "val": 150, "test": 150},
        "target_unique_aircraft_per_cell": {"train": 200, "val": 100, "test": 100},
    }
    plan = {
        "plan_version": 1,
        "overlays": [
            {"family": "constant_deviation", "tier": "moderate", "duration_seconds": 120,
             "quota_target": {"episodes": 50, "unique_aircraft": 40}},
        ],
    }
    assert plan_mode(plan) == "quota"
    overlays = overlays_from_plan(cfg, plan)
    assert overlays[0].tau == 0.0  # unused in quota mode
    targets = quota_targets_from_plan(cfg, plan)
    key = overlays[0].overlay_key
    assert targets[key].episodes == {"train": 50, "val": 50, "test": 50}
    assert targets[key].unique_aircraft == {"train": 40, "val": 40, "test": 40}


def test_quota_targets_from_plan_falls_back_to_config_defaults():
    cfg = config()
    cfg["quota_mode"] = {
        "target_episodes_per_cell": {"train": 300, "val": 150, "test": 150},
        "target_unique_aircraft_per_cell": {"train": 200, "val": 100, "test": 100},
    }
    plan = {
        "plan_version": 1,
        "overlays": [
            {"family": "constant_deviation", "tier": "moderate", "duration_seconds": 120,
             "quota_target": True},
        ],
    }
    targets = quota_targets_from_plan(cfg, plan)
    key = overlays_from_plan(cfg, plan)[0].overlay_key
    assert targets[key].episodes == {"train": 300, "val": 150, "test": 150}
    assert targets[key].unique_aircraft == {"train": 200, "val": 100, "test": 100}


def test_plan_mode_rejects_mixed_selection():
    plan = {
        "plan_version": 1,
        "overlays": [
            {"family": "constant_deviation", "tier": "moderate", "duration_seconds": 120, "tau": 0.005},
            {"family": "freeze_fixed_value", "tier": "moderate", "duration_seconds": 120,
             "quota_target": {"episodes": 1, "unique_aircraft": 1}},
        ],
    }
    with pytest.raises(ValueError, match="all-tau"):
        plan_mode(plan)


def test_dry_run_summary_returns_counts_without_writing(tmp_path):
    import pandas as pd

    rows = []
    for aircraft in ("a00001", "a00002", "a00003"):
        for i in range(100):
            row = {"icao24": aircraft, "segment_id": 0, "time": i * 10, "lat": 30 + i * .001, "lon": 10 + i * .001,
                   "velocity": 200.0, "heading": 90.0, "vertrate": 1.0, "baroaltitude": 3000.0 + i,
                   "geoaltitude": 3010.0 + i, "onground": False, "contact_lag_seconds": 0.0, "contact_lag_missing": False}
            row.update({f"{field}_missing": False for field in ("lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude")})
            rows.append(row)
    df = pd.DataFrame(rows)
    summary = dry_run_summary(df, overlay_from_config(config(), "constant_deviation", "moderate", tau=0.0), 3, lambda _icao: "train", max_segments_per_chunk=1)
    assert summary["input_rows"] == 300
    assert summary["eligible_segments"] == 3
    assert summary["selected_segments"] == 0
    assert not list(tmp_path.iterdir())
