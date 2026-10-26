"""Stage 1 overlay generation CLI. Do not run before the human gate."""
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

from dataclasses import asdict

from flids.attacks.config import load_approved_config, load_run_plan
from flids.attacks.run_config import dry_run_summary, overlay_from_config, overlays_from_plan
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
    parser.add_argument("--plan", type=Path, default=None,
                        help="run-plan YAML listing overlays; mutually exclusive with the explicit overlay flags")
    parser.add_argument("--family", choices=FAMILIES, action="append", default=None,
                        help="overlay family; repeat to select several (explicit-flag mode)")
    parser.add_argument("--tier", choices=("subtle", "moderate", "blatant", "gross_positive_control"), default=None)
    parser.add_argument("--tau", type=float, default=None)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--onset-mode", choices=("linear_mix", "abrupt"), default="linear_mix")
    parser.add_argument("--altitude-variant", choices=("baro_only", "baro_plus_geo"), default="baro_only")
    parser.add_argument("--episodes-per-segment", type=int, default=1)
    parser.add_argument("--segments-per-chunk", type=int, default=64)
    parser.add_argument("--progress-log", type=Path, default=None,
                        help="append chunk progress events (JSON lines) to this file")
    return parser


def _resolve_overlays(args, config) -> tuple:
    """Build overlays from a run plan or from explicit flags.

    The default invocation no longer silently generates a pilot: without
    ``--plan`` the caller must pass ``--family``, ``--tier``, ``--tau`` and
    ``--duration-seconds`` explicitly.
    """
    explicit = (args.family, args.tier, args.tau, args.duration_seconds)
    if args.plan is not None:
        if any(value is not None for value in explicit):
            raise SystemExit("--plan cannot be combined with --family/--tier/--tau/--duration-seconds")
        return overlays_from_plan(config, load_run_plan(args.plan))
    missing = [
        name for name, value in (
            ("--family", args.family), ("--tier", args.tier),
            ("--tau", args.tau), ("--duration-seconds", args.duration_seconds),
        ) if value is None
    ]
    if missing:
        raise SystemExit(
            "provide --plan, or all of --family/--tier/--tau/--duration-seconds "
            f"(missing: {', '.join(missing)})"
        )
    return tuple(overlay_from_config(
        config,
        family,
        args.tier,
        tau=args.tau,
        duration_seconds=args.duration_seconds,
        altitude_variant=args.altitude_variant,
        episodes_per_segment=args.episodes_per_segment,
        onset_mode=args.onset_mode,
    ) for family in args.family)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config_path = args.config.resolve()
    config = load_approved_config(config_path)
    overlays = _resolve_overlays(args, config)
    resolved_plan = [asdict(overlay) for overlay in overlays]
    print(json.dumps({"resolved_plan": resolved_plan}, indent=2, sort_keys=True))
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
            overlays,
            args.seed,
            split_map.split_of,
            max_segments_per_chunk=args.segments_per_chunk,
        )
        summary["overlay_merge_order"] = [overlay.overlay_key for overlay in overlays]
        summary["resolved_plan"] = resolved_plan
        summary["seed"] = args.seed
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    progress_log = None
    if args.progress_log is not None:
        progress_path = args.progress_log if args.progress_log.is_absolute() else ROOT / args.progress_log
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_log = progress_path.open("a", encoding="utf-8")

    def progress_callback(event: dict) -> None:
        _print_progress(event)
        if progress_log is not None:
            progress_log.write(json.dumps(event, sort_keys=True) + "\n")
            progress_log.flush()

    try:
        manifest = write_overlay_tables(
            frame,
            overlays,
            args.seed,
            split_map.split_of,
            config,
            config_path=config_path,
            output_dir=resolved_out,
            resolved_plan=resolved_plan,
            max_segments_per_chunk=args.segments_per_chunk,
            repo_root=ROOT,
            progress_callback=progress_callback,
        )
    finally:
        if progress_log is not None:
            progress_log.close()
    print(json.dumps({"output": str(resolved_out), "manifest": manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
