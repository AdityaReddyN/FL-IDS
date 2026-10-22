"""Read-only, in-memory smoke/performance check for the v3 assembler.

Written for Phase 1 review; do not run it as part of generation.  It writes no
files and deliberately uses explicit Python overlays rather than YAML.
"""
from __future__ import annotations

import argparse
import sys
import time
import tracemalloc
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd

from flids.attacks.assembler import OverlaySpec, assemble_overlay
from flids.attacks.splits import load_split_aircraft


def overlays():
    base = dict(tier="small", duration_seconds=120, tau=.2, episodes_per_segment=1)
    return (
        OverlaySpec("constant_deviation", subtype="constant", magnitude_m=500., **base),
        OverlaySpec("random_gaussian_deviation", subtype="gaussian", sigma_m=500., **base),
        OverlaySpec("gradual_deviation", subtype="gradual", magnitude_m=1000., **base),
        OverlaySpec("altitude_constant_deviation", subtype="baro_only", altitude_variant="baro_only", shift_m=35., **base),
        OverlaySpec("replay_partial_field", subtype="partial", **base),
        OverlaySpec("replay_full_field", subtype="full", **base),
        OverlaySpec("freeze_fixed_value", subtype="freeze", **base),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/processed/opensky_clean_v1.parquet"))
    parser.add_argument("--splits", type=Path, default=Path("data/sequences_v2/split_aircraft.json"))
    parser.add_argument("--seed", type=int, default=20261022)
    args = parser.parse_args()
    source = pd.read_parquet(args.data)
    split_map = load_split_aircraft(args.splits)
    train = source[source.icao24.map(split_map.split_of) == "train"]
    keys = train[["icao24", "segment_id"]].drop_duplicates().sample(n=min(300, train.groupby(["icao24", "segment_id"]).ngroups), random_state=args.seed)
    sample = train.merge(keys, on=["icao24", "segment_id"], how="inner")
    total_segments = source.groupby(["icao24", "segment_id"]).ngroups
    for overlay in overlays():
        tracemalloc.start(); started = time.perf_counter()
        tables = assemble_overlay(sample, overlay, args.seed, split_map.split_of)
        elapsed = time.perf_counter() - started; _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        rejected = tables.rejected_candidates.groupby("reason").size().to_dict()
        windows = tables.windows.groupby("label").size().to_dict()
        strata = tables.windows.groupby("stratum").size().to_dict()
        effective = int(tables.attacked_rows.is_attack_row.sum())
        eligible = tables.segments.eligible.sum(); selected = tables.segments.selected.sum()
        print(overlay.attack_family, {"overlay_key": overlay.overlay_key, "accepted": len(tables.episodes), "rejected_by_reason": rejected, "selection_fraction": selected / eligible if eligible else 0., "tau_requested": overlay.tau, "effective_rows": effective, "windows": {**windows, **strata}, "peak_python_mb": peak / 1e6, "seconds_per_100_segments": elapsed * 100 / len(keys), "extrapolated_seconds_all_21389": elapsed * total_segments / len(keys)})


if __name__ == "__main__":
    main()
