"""Read-only diagnostic for frozen or on-ground normal v2 source windows.

No data artifact is changed. A window is "constant" only when all 30 source
rows have finite lat/lon/velocity and each field has zero range. "Effectively
frozen" is the union of constant windows and windows containing any onground
source row; the separate counts are reported to avoid conflating the two.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/sequences_v2")
    parser.add_argument("--cleaned-data", default="data/processed/opensky_clean_v1.parquet")
    parser.add_argument("--splits", nargs="+", choices=("train", "val", "test"), default=("train", "val", "test"))
    parser.add_argument("--seed", type=int, default=42, help="Recorded for CLI consistency; unused because this diagnostic is deterministic.")
    return parser.parse_args()


def is_constant(window: pd.DataFrame) -> bool:
    values = window[["lat", "lon", "velocity"]].to_numpy(dtype=float)
    return bool(np.isfinite(values).all() and np.all(np.ptp(values, axis=0) == 0.0))


def main() -> None:
    args = parse_args()
    print("Reading immutable cleaned state vectors...", flush=True)
    source = pd.read_parquet(args.cleaned_data, columns=["icao24", "segment_id", "time", "lat", "lon", "velocity", "onground"])
    source = source.sort_values(["icao24", "segment_id", "time"]).reset_index(drop=True)
    groups = {key: group.reset_index(drop=True) for key, group in source.groupby(["icao24", "segment_id"], sort=False)}
    print(f"Indexed {len(groups):,} aircraft/segment groups.", flush=True)

    total = constant = onground = frozen = 0
    for split in args.splits:
        metadata = pd.read_parquet(f"{args.data_dir}/{split}_metadata.parquet")
        normal = metadata.loc[metadata["label"] == 0]
        split_constant = split_onground = split_frozen = 0
        for row in normal.itertuples(index=False):
            window = groups[(row.icao24, row.segment_id)].iloc[row.source_start_offset : row.source_end_offset + 1]
            constant_here = is_constant(window)
            onground_here = bool(window["onground"].fillna(False).astype(bool).any())
            split_constant += constant_here
            split_onground += onground_here
            split_frozen += constant_here or onground_here
        total += len(normal)
        constant += split_constant
        onground += split_onground
        frozen += split_frozen
        print(f"{split}: normal={len(normal)} constant_lat_lon_velocity={split_constant} onground_any={split_onground} effectively_frozen={split_frozen}", flush=True)

    label = "all" if len(args.splits) == 3 else "+".join(args.splits)
    print(f"{label}: normal={total} constant_lat_lon_velocity={constant} ({constant / total:.2%})")
    print(f"{label}: onground_any={onground} ({onground / total:.2%})")
    print(f"{label}: effectively_frozen_union={frozen} ({frozen / total:.2%})")


if __name__ == "__main__":
    main()
