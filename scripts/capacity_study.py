"""Read-only capacity study for candidate Stage 1 overlays.

Run this yourself; it reads the immutable cleaned table and the fixed aircraft
split and writes one JSON report. It generates no attacks, windows, or datasets
and modifies nothing. For each candidate overlay (family x tier, and
duration x onset_mode) and split it reports eligible segments, eligible starts,
and unique aircraft, plus a descriptive estimate of how many such overlays a
merged dataset could host at one overlay per segment given the quota targets in
the config.

This informs the proposed dataset plan (D-039); it does not change the YAML or
select anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.attacks.config import load_approved_config  # noqa: E402
from flids.attacks.quota import overlay_capacity  # noqa: E402
from flids.attacks.run_config import overlay_from_config  # noqa: E402
from flids.attacks.splits import SPLIT_NAMES, load_split_aircraft  # noqa: E402

# Candidate grid. Durations are paired with onset modes; gradual needs a long
# duration (>= 5 effective rows), so it is studied only at 600/900 s.
TIERS = ("subtle", "moderate", "blatant")
DURATIONS = (120.0, 600.0, 900.0)
ONSET_MODES = ("linear_mix", "abrupt")


def _candidates(config: dict) -> list[dict]:
    families = ("constant_deviation", "random_gaussian_deviation", "gradual_deviation",
                "altitude_constant_deviation", "replay_partial_field", "replay_full_field",
                "freeze_fixed_value")
    out = []
    for family in families:
        for tier in TIERS:
            for duration in DURATIONS:
                if family == "gradual_deviation" and duration < 600.0:
                    continue  # < 5 effective rows; OverlaySpec would reject
                for onset in ONSET_MODES:
                    out.append({"family": family, "tier": tier,
                                "duration_seconds": duration, "onset_mode": onset})
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "attack_v3_stage1.yaml")
    parser.add_argument("--input", type=Path, default=Path("data/processed/opensky_clean_v1.parquet"))
    parser.add_argument("--splits", type=Path, default=Path("data/sequences_v2/split_aircraft.json"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("results/capacity_study_v1/report.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_approved_config(args.config.resolve())
    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    split_path = args.splits if args.splits.is_absolute() else ROOT / args.splits
    split_map = load_split_aircraft(split_path)
    print("Reading immutable cleaned table...", flush=True)
    df = pd.read_parquet(input_path)

    quota_mode = config.get("quota_mode", {}) or {}
    episode_targets = quota_mode.get("target_episodes_per_cell", {})

    results = []
    for entry in _candidates(config):
        try:
            overlay = overlay_from_config(
                config, entry["family"], entry["tier"],
                duration_seconds=entry["duration_seconds"], onset_mode=entry["onset_mode"],
            )
        except ValueError as error:
            results.append({**entry, "skipped": str(error)})
            continue
        capacity = overlay_capacity(df, overlay, args.seed, split_map.split_of)
        per_split = {}
        for split in SPLIT_NAMES:
            cell = capacity[split]
            target = int(episode_targets.get(split, 0)) or None
            cell_out = dict(cell)
            cell_out["overlays_that_fit_at_one_per_segment"] = (
                cell["eligible_segments"] // target if target else None
            )
            per_split[split] = cell_out
        results.append({**entry, "overlay_key": overlay.overlay_key, "per_split": per_split})

    report = {
        "parameters": {"config": str(args.config), "input": str(input_path),
                       "splits": str(split_path), "seed": args.seed,
                       "episode_targets_per_cell": episode_targets},
        "candidates": results,
    }
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Studied {len(results)} candidate overlays.")
    for item in results[:8]:
        if "skipped" in item:
            print(f"  {item['family']}/{item['tier']} {int(item['duration_seconds'])}s "
                  f"{item['onset_mode']}: skipped ({item['skipped']})")
            continue
        train = item["per_split"]["train"]
        print(f"  {item['family']}/{item['tier']} {int(item['duration_seconds'])}s "
              f"{item['onset_mode']}: train eligible_segments={train['eligible_segments']}, "
              f"unique_aircraft={train['unique_aircraft']}, "
              f"fit={train['overlays_that_fit_at_one_per_segment']}")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    main()
