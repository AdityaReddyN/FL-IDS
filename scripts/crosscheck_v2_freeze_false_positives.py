"""Read-only cross-check of normal-to-freeze v2 LSTM false positives.

Matches prediction rows to immutable v2 test metadata and then to their source
state-vector rows. It reports overlap with the frozen definition (constant
finite lat/lon/velocity or any on-ground source row), on-ground rows, and any
core-feature missingness. It does not write or alter data/results artifacts.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


CORE_FEATURES = ["lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/sequences_v2"))
    parser.add_argument("--predictions", type=Path, default=Path("results/E-001/run1/test_predictions.csv"))
    parser.add_argument("--cleaned-data", type=Path, default=Path("data/processed/opensky_clean_v1.parquet"))
    parser.add_argument("--seed", type=int, default=42, help="Recorded for CLI consistency; unused because this is deterministic.")
    return parser.parse_args()


def is_constant(window: pd.DataFrame) -> bool:
    values = window[["lat", "lon", "velocity"]].to_numpy(dtype=float)
    return bool(np.isfinite(values).all() and np.all(np.ptp(values, axis=0) == 0.0))


def main() -> None:
    args = parse_args()
    predictions = pd.read_csv(args.predictions)
    false_positives = predictions.loc[
        (predictions["true_label"] == 0) & (predictions["predicted_label"] == 4),
        "example_index",
    ]
    metadata = pd.read_parquet(args.data_dir / "test_metadata.parquet")
    rows = metadata.set_index("example_index").loc[false_positives]
    source = pd.read_parquet(
        args.cleaned_data,
        columns=["icao24", "segment_id", "time", "onground", *CORE_FEATURES],
    ).sort_values(["icao24", "segment_id", "time"])
    groups = {key: group.reset_index(drop=True) for key, group in source.groupby(["icao24", "segment_id"], sort=False)}

    constant = onground = missing = frozen = 0
    for row in rows.itertuples():
        window = groups[(row.icao24, row.segment_id)].iloc[row.source_start_offset : row.source_end_offset + 1]
        constant_here = is_constant(window)
        onground_here = bool(window["onground"].fillna(False).astype(bool).any())
        missing_here = bool(window[CORE_FEATURES].isna().any(axis=None))
        constant += constant_here
        onground += onground_here
        missing += missing_here
        frozen += constant_here or onground_here

    total = len(rows)
    print(f"normal_to_freeze_false_positives={total}")
    print(f"constant_lat_lon_velocity={constant} ({constant / total:.2%})")
    print(f"onground_any={onground} ({onground / total:.2%})")
    print(f"effectively_frozen_union={frozen} ({frozen / total:.2%})")
    print(f"any_core_feature_missing={missing} ({missing / total:.2%})")


if __name__ == "__main__":
    main()
