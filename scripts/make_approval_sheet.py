"""Print a read-only inventory of provisional Stage 1 configuration values."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.attacks.eligibility import REQUIRED_FIELDS
from flids.attacks.episode import MIN_EFFECTIVE_ROWS, NOOP_MIN_ALTITUDE_M, NOOP_MIN_HORIZONTAL_M
from flids.attacks.placement import MAX_SPAN_FACTOR, MIN_SPAN_FACTOR


def rows(config: dict) -> list[tuple[str, str, str]]:
    attacks = config["attacks"]
    episodes = config["episodes"]
    tiers = config["tiers"]
    prevalence = config["prevalence"]
    quota = config["quota_mode"]
    return [
        ("Horizontal magnitudes by tier", str(tiers["horizontal_meters"]), "D-022"),
        ("Gaussian sigma by tier", str(attacks["gaussian"]["deviation_sigma_meters_by_tier"]), "D-022"),
        ("Eq. 12 kappa by tier", str(attacks["gaussian"]["eq12_noise_kappa_by_tier"]), "D-022"),
        ("Eq. 12 per-step sigma", str(attacks["gaussian"]["per_step_noise_sigma_meters"]), "D-022"),
        ("Altitude shifts by tier", str(tiers["altitude_residual_calibration_meters"]["shared_shift_both_variants"]), "D-022"),
        ("Target episode quotas by split", str(quota["target_episodes_per_cell"]), "D-020 / D-018; provisional quota matrix"),
        ("Target unique-aircraft quotas by split", str(quota["target_unique_aircraft_per_cell"]), "D-020 / D-018; provisional quota matrix"),
        ("REQUIRED_FIELDS", str(REQUIRED_FIELDS), "D-021; provisional field requirements"),
        ("Actual span factor lower/upper", f"{MIN_SPAN_FACTOR}, {MAX_SPAN_FACTOR}", "D-021; provisional span filter"),
        ("Horizontal / altitude no-op thresholds", f"{NOOP_MIN_HORIZONTAL_M} m / {NOOP_MIN_ALTITUDE_M} m", "D-024; provisional no-op guard"),
        ("Nominal / long durations", f"{episodes['nominal_duration_seconds']} s / {episodes['long_episode_durations_seconds']} s", "D-019/D-020; long-duration feasibility"),
        ("Freeze duration tiers", str(episodes["freeze_duration_tiers_seconds"]), "D-017; proposed freeze tiers"),
        ("Ramp mode / steps / minimum effective rows", f"{episodes['onset']['default_mode']} / {episodes['onset']['default_steps']} / {MIN_EFFECTIVE_ROWS}", "D-022 ramp; D-024 effective-row rule"),
        ("Selection tau sweep", str(prevalence["tau_sweep"]), "D-025/D-028; eligible-segment Bernoulli probability"),
        ("Replay delay / tolerance", f"{config['eligibility']['replay']['paper_grounded_delay_seconds']} s / {config['eligibility']['replay']['timestamp_tolerance_seconds']} s", "D-021; 300 s paper-grounded, tolerance implementation value"),
        ("Geoaltitude glitch screen", f"q99.9 = {config['eligibility']['geoaltitude_glitch_screen']['train_only_q999_threshold_meters']} m", "D-019; proposed train-only screen"),
        ("Minimum episode gap / max per segment", f"{episodes['minimum_inter_episode_gap_seconds']} s / {episodes['max_per_segment']}", "D-021/D-019; placement constraints"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/attack_v3_stage1.yaml")
    args = parser.parse_args()
    with args.config.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    print(f"Config: {args.config}\nStatus: {config.get('status')} (this script does not change it)\n")
    print(f"{'PROVISIONAL VALUE':52} | {'VALUE':72} | SOURCE / DECISION")
    print("-" * 155)
    for name, value, source in rows(config):
        print(f"{name:52} | {value:72} | {source}")


if __name__ == "__main__":
    main()
