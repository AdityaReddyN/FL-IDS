"""CLI-resolution tests for scripts/generate_attack_v3.py (no data IO)."""

import argparse
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_cli():
    path = ROOT / "scripts" / "generate_attack_v3.py"
    spec = importlib.util.spec_from_file_location("generate_attack_v3", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config():
    return {
        "episodes": {"nominal_duration_seconds": 120, "minimum_inter_episode_gap_seconds": 600,
                     "freeze_duration_tiers_seconds": {"moderate": 120}, "onset": {"default_steps": 3}},
        "attacks": {"gaussian": {"deviation_sigma_meters_by_tier": {"moderate": 1250.0},
                                 "eq12_noise_kappa_by_tier": {"moderate": 0.1}, "per_step_noise_sigma_meters": 25.0}},
        "tiers": {"horizontal_meters": {"moderate": 2500.0},
                  "altitude_residual_calibration_meters": {"shared_shift_both_variants": {"moderate": 125.0}}},
        "region": {"primary_dataset_mode": "uniform_per_subairspace"},
        "prevalence": {"tau_sweep": [0.005, 0.01]},
        "eligibility": {"replay": {"paper_grounded_delay_seconds": 300, "timestamp_tolerance_seconds": 5},
                        "geoaltitude_glitch_screen": {"train_only_q999_threshold_meters": 2887.98}},
    }


def _args(**overrides):
    base = dict(plan=None, family=None, tier=None, tau=None, duration_seconds=None,
                altitude_variant="baro_only", episodes_per_segment=1, onset_mode="linear_mix")
    base.update(overrides)
    return argparse.Namespace(**base)


def test_default_invocation_refuses_silent_pilot():
    cli = _load_cli()
    with pytest.raises(SystemExit, match="provide --plan"):
        cli._resolve_overlays(_args(), _config())


def test_plan_and_explicit_flags_are_mutually_exclusive(tmp_path):
    cli = _load_cli()
    with pytest.raises(SystemExit, match="cannot be combined"):
        cli._resolve_overlays(_args(plan=tmp_path / "p.yaml", family=["constant_deviation"]), _config())


def test_explicit_flags_build_overlays():
    cli = _load_cli()
    overlays = cli._resolve_overlays(
        _args(family=["constant_deviation"], tier="moderate", tau=0.005,
              duration_seconds=120.0, onset_mode="abrupt"),
        _config(),
    )
    assert len(overlays) == 1
    assert overlays[0].attack_family == "constant_deviation"
    assert overlays[0].onset_mode == "abrupt"
