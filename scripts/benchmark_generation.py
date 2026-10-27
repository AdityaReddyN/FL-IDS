"""Throughput benchmark for Stage 1 generation on a working subset (human-run).

Dry benchmark: assembles overlays in memory on a subset of the cleaned source
(a few parts or a capped aircraft count), times it, and extrapolates to the full
source. Writes nothing. Use it to size a full generation run before committing to
it; it does not create a dataset, so it needs no clean tree.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.attacks.assembler import assemble_overlays  # noqa: E402
from flids.attacks.config import load_approved_config, load_run_plan  # noqa: E402
from flids.attacks.quota import select_quota_segments  # noqa: E402
from flids.attacks.run_config import overlays_from_plan, quota_targets_from_plan  # noqa: E402


def benchmark(frame: pd.DataFrame, overlays, seed: int, split_of, quota_targets=None) -> dict:
    """Assemble overlays in memory on ``frame`` and return timing/throughput."""
    n_rows = int(len(frame))
    n_segments = int(frame.groupby(["icao24", "segment_id"], sort=False).ngroups)
    started = time.perf_counter()
    chosen = None
    if quota_targets is not None:
        chosen = select_quota_segments(frame, overlays, seed, split_of, quota_targets,
                                       fail_on_capacity_shortfall=False)["chosen"]
    tables = assemble_overlays(frame, overlays, seed, split_of, chosen_segments=chosen)
    elapsed = time.perf_counter() - started
    episodes = int(len(tables.episodes))
    return {
        "rows": n_rows, "segments": n_segments, "accepted_episodes": episodes,
        "elapsed_seconds": elapsed,
        "rows_per_second": (n_rows / elapsed) if elapsed else None,
        "segments_per_second": (n_segments / elapsed) if elapsed else None,
    }


def _load_subset(clean_dir: Path, max_parts: int | None, max_aircraft: int | None) -> pd.DataFrame:
    parts = sorted(clean_dir.glob("part_*.parquet"))
    if not parts:
        raise SystemExit(f"no part_*.parquet in {clean_dir}")
    if max_parts is not None:
        parts = parts[:max_parts]
    frame = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    if max_aircraft is not None:
        keep = frame["icao24"].drop_duplicates().head(max_aircraft)
        frame = frame[frame["icao24"].isin(keep)].reset_index(drop=True)
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "attack_v3_stage1.yaml")
    parser.add_argument("--clean-dir", type=Path, default=Path("data/processed/hdd_clean_v1"))
    parser.add_argument("--max-parts", type=int, default=2)
    parser.add_argument("--max-aircraft", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = load_approved_config(args.config.resolve())
    plan = load_run_plan(args.plan)
    overlays = overlays_from_plan(config, plan)
    quota_targets = quota_targets_from_plan(config, plan)
    clean_dir = args.clean_dir if args.clean_dir.is_absolute() else ROOT / args.clean_dir

    split = json.loads((clean_dir / "split_aircraft.json").read_text(encoding="utf-8"))
    split_of = {str(ic): name for name, ids in split.items() for ic in ids}.get
    frame = _load_subset(clean_dir, args.max_parts, args.max_aircraft)
    result = benchmark(frame, overlays, args.seed, lambda ic: split_of(str(ic)), quota_targets)

    manifest = clean_dir / "manifest.json"
    if manifest.exists():
        full = json.loads(manifest.read_text(encoding="utf-8"))
        total_rows, total_segments = full.get("rows"), full.get("segments")
        if result["rows_per_second"] and total_rows:
            result["extrapolated_full_run"] = {
                "total_rows": total_rows, "total_segments": total_segments,
                "estimated_seconds": total_rows / result["rows_per_second"],
                "estimated_minutes": total_rows / result["rows_per_second"] / 60.0,
            }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
