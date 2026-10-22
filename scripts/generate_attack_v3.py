"""Stage 1 single-overlay generation CLI. Do not run before the human gate."""
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

from flids.attacks.config import load_approved_config
from flids.attacks.run_config import dry_run_summary, overlay_from_config
from flids.attacks.splits import load_split_aircraft
from flids.attacks.writer import write_overlay_tables


FAMILIES = (
    "constant_deviation", "random_gaussian_deviation", "gradual_deviation",
    "altitude_constant_deviation", "replay_partial_field", "replay_full_field",
    "freeze_fixed_value",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "attack_v3_stage1.yaml")
    parser.add_argument("--out", type=Path, required=True, help="new run directory under data/attack_generation_v3")
    parser.add_argument("--dry-run", action="store_true", help="print counts only; write nothing")
    parser.add_argument("--family", choices=FAMILIES, default="constant_deviation")
    parser.add_argument("--tier", choices=("subtle", "moderate", "blatant", "gross_positive_control"), default="moderate")
    parser.add_argument("--tau", type=float, default=None)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--altitude-variant", choices=("baro_only", "baro_plus_geo"), default="baro_only")
    parser.add_argument("--episodes-per-segment", type=int, default=1)
    parser.add_argument("--segments-per-chunk", type=int, default=64)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config_path = args.config.resolve()
    config = load_approved_config(config_path)
    overlay = overlay_from_config(
        config,
        args.family,
        args.tier,
        tau=args.tau,
        duration_seconds=args.duration_seconds,
        altitude_variant=args.altitude_variant,
        episodes_per_segment=args.episodes_per_segment,
    )
    input_path = Path(config["input"]["cleaned_table"])
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    split_path = Path(config["splits"]["fixed_aircraft_split"])
    if not split_path.is_absolute():
        split_path = ROOT / split_path
    split_map = load_split_aircraft(split_path)
    frame = pd.read_parquet(input_path)

    requested_out = args.out if args.out.is_absolute() else ROOT / args.out
    allowed_root = (ROOT / "data" / "attack_generation_v3").resolve()
    resolved_out = requested_out.resolve()
    if allowed_root not in resolved_out.parents:
        raise SystemExit(f"--out must be a new run directory beneath {allowed_root}")

    if args.dry_run:
        summary = dry_run_summary(
            frame,
            overlay,
            args.seed,
            split_map.split_of,
            max_segments_per_chunk=args.segments_per_chunk,
        )
        summary["overlay_key"] = overlay.overlay_key
        summary["seed"] = args.seed
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    manifest = write_overlay_tables(
        frame,
        overlay,
        args.seed,
        split_map.split_of,
        config,
        config_path=config_path,
        output_dir=resolved_out,
        max_segments_per_chunk=args.segments_per_chunk,
        repo_root=ROOT,
    )
    print(json.dumps({"output": str(resolved_out), "manifest": manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
