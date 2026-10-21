"""Read-only window-yield check on real train segments (D-024).

WRITE ONLY: this script has NOT been run. It creates no attacks, windows, or
datasets on disk; it only labels synthetic in-memory episode placements built
on existing eligibility masks, writes one JSON report, and prints a summary.

For each requested duration it places one ``linear_mix`` episode uniformly on
the eligible, span-filtered starts of each of 1,000 randomly sampled train
segments (seeded). Episode multipliers come from ``ramps.ramp_multipliers``;
no rows are modified. ``windows.label_windows`` is then used to count, per
episode, the windows labelled ``attacked`` (the "qualifying" windows in the
earlier calibration), ``ambiguous``, and ``interior_only``.

Reference means from the earlier calibration:

* 600 s: 7.85 qualifying and 2.50 interior-only windows per episode
* 900 s: 10.84 qualifying and 5.50 interior-only windows per episode

The script prints the differences. It does not tune eligibility, placement,
stride, or thresholds to match those numbers; differences are expected.

Run this script yourself. It never opens
``docs/calibration_v3_stage1.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.attacks.eligibility import (  # noqa: E402
    REQUIRED_FIELDS,
    eligible_starts,
    pair_valid,
    row_eligible,
)
from flids.attacks.placement import (  # noqa: E402
    filter_starts_by_span,
    rows_for_duration,
)
from flids.attacks.ramps import ramp_multipliers  # noqa: E402
from flids.attacks.schemas import FEATURE_FIELDS  # noqa: E402
from flids.attacks.splits import (  # noqa: E402
    load_split_aircraft,
    validate_splits,
)
from flids.attacks.windows import (  # noqa: E402
    WINDOW_ROWS,
    WINDOW_STRIDE,
    label_windows,
)

SPAN_DURATIONS = (120.0, 600.0, 900.0)
REFERENCE_MEANS = {
    600.0: {"attacked": 7.85, "interior_only": 2.50},
    900.0: {"attacked": 10.84, "interior_only": 5.50},
}
WINDOW_ROWS_DEFAULT = WINDOW_ROWS
WINDOW_STRIDE_DEFAULT = WINDOW_STRIDE


class _SingleSegmentRows:
    """Minimal single-segment view for ``eligible_starts`` validation."""

    def __init__(self, icao24: str, segment_id: int, length: int) -> None:
        self.columns = ("icao24", "segment_id")
        self._key_columns = {
            "icao24": pd.Series([icao24]),
            "segment_id": pd.Series([segment_id]),
        }
        self._length = length

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, column: str) -> pd.Series:
        return self._key_columns[column]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/opensky_clean_v1.parquet"),
    )
    parser.add_argument(
        "--splits",
        type=Path,
        default=Path("data/sequences_v2/split_aircraft.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results/windows_check_v3/report.json"),
    )
    parser.add_argument("--segments", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _mean(values: list[float]) -> float | None:
    return round(float(np.mean(values)), 4) if values else None


def _segment_masks(segment_df: pd.DataFrame):
    rows = row_eligible(
        segment_df, REQUIRED_FIELDS["replay_full_field"]
    )
    pairs = pair_valid(segment_df)
    return rows, pairs


def build_segment_arrays(n_segment: int, start: int, n_rows: int):
    multipliers = np.zeros(n_segment)
    positions = np.full(n_segment, "none", dtype=object)
    episode_ids = np.full(n_segment, -1, dtype=np.int64)
    ramp, ramp_positions = ramp_multipliers(n_rows, 3, "linear_mix")
    stop = start + n_rows
    multipliers[start:stop] = ramp
    positions[start:stop] = ramp_positions
    episode_ids[start:stop] = 0
    return multipliers, positions, episode_ids


def main() -> None:
    args = parse_args()
    columns = [
        "icao24",
        "segment_id",
        "time",
        "onground",
        "contact_lag_seconds",
        "contact_lag_missing",
        *FEATURE_FIELDS,
        *(f"{field}_missing" for field in FEATURE_FIELDS),
    ]
    print("Reading immutable cleaned table...", flush=True)
    df = pd.read_parquet(args.input, columns=columns)
    df = df.sort_values(
        ["icao24", "segment_id", "time"], kind="mergesort"
    ).reset_index(drop=True)

    splits = load_split_aircraft(args.splits)
    validate_splits(splits, df["icao24"].unique())
    split_series = df["icao24"].map(splits.assignments)
    if split_series.isna().any():
        raise ValueError("aircraft missing from the split file")
    split_rows = split_series.to_numpy(dtype=object)

    group_items = [
        (key, np.asarray(indices, dtype=np.int64))
        for key, indices in df.groupby(
            ["icao24", "segment_id"], sort=False
        ).indices.items()
    ]
    longest = max(SPAN_DURATIONS)
    longest_rows = rows_for_duration(longest)

    train_segments = [
        (key, positions)
        for key, positions in group_items
        if split_rows[positions[0]] == "train"
        and positions.size >= longest_rows
    ]
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(train_segments))
    sampled = []
    for index in order:
        key, positions = train_segments[int(index)]
        segment_df = df.iloc[positions].reset_index(drop=True)
        rows, pairs = _segment_masks(segment_df)
        times = segment_df["time"].to_numpy(dtype=float)
        view = _SingleSegmentRows(key[0], key[1], positions.size)
        starts = eligible_starts(view, longest_rows, rows, pairs)
        kept, _ = filter_starts_by_span(
            starts, times, longest_rows, longest
        )
        if kept.size:
            sampled.append((key, positions))
        if len(sampled) >= args.segments:
            break
    if len(sampled) < args.segments:
        print(
            f"Only {len(sampled):,} train segments support the longest "
            f"duration; using those."
        )

    per_duration = {
        duration: {
            "n_episodes": 0,
            "n_segments_without_start": 0,
            "attacked": [],
            "ambiguous": [],
            "interior_only": [],
            "n_windows": [],
        }
        for duration in SPAN_DURATIONS
    }

    for key, positions in sampled:
        segment_df = df.iloc[positions].reset_index(drop=True)
        rows, pairs = _segment_masks(segment_df)
        times = segment_df["time"].to_numpy(dtype=float)
        view = _SingleSegmentRows(key[0], key[1], positions.size)
        n_segment = positions.size

        for duration in SPAN_DURATIONS:
            n_rows = rows_for_duration(duration)
            starts = eligible_starts(view, n_rows, rows, pairs)
            kept, _ = filter_starts_by_span(
                starts, times, n_rows, duration
            )
            entry = per_duration[duration]
            if kept.size == 0:
                entry["n_segments_without_start"] += 1
                continue

            start = int(kept[int(rng.integers(kept.size))])
            multipliers, label_positions, episode_ids = (
                build_segment_arrays(n_segment, start, n_rows)
            )
            windows = label_windows(
                multipliers,
                label_positions,
                episode_ids,
                window_rows=WINDOW_ROWS_DEFAULT,
                stride=WINDOW_STRIDE_DEFAULT,
            )
            episode_windows = [
                window
                for window in windows
                if window["episode_id"] == 0
            ]
            entry["n_episodes"] += 1
            entry["attacked"].append(
                float(
                    sum(
                        window["label"] == "attacked"
                        for window in episode_windows
                    )
                )
            )
            entry["ambiguous"].append(
                float(
                    sum(
                        window["label"] == "ambiguous"
                        for window in episode_windows
                    )
                )
            )
            entry["interior_only"].append(
                float(
                    sum(
                        window["stratum"] == "interior_only"
                        for window in episode_windows
                    )
                )
            )
            entry["n_windows"].append(float(len(episode_windows)))

    report = {
        "parameters": {
            "input": str(args.input),
            "splits": str(args.splits),
            "segments_requested": args.segments,
            "segments_used": len(sampled),
            "seed": args.seed,
            "durations_seconds": list(SPAN_DURATIONS),
            "window_rows": WINDOW_ROWS_DEFAULT,
            "window_stride": WINDOW_STRIDE_DEFAULT,
            "onset_mode": "linear_mix",
            "ramp_rows": 3,
        },
        "reference_means": {
            str(int(duration)): values
            for duration, values in REFERENCE_MEANS.items()
        },
        "per_duration": {},
    }

    for duration in SPAN_DURATIONS:
        entry = per_duration[duration]
        means = {
            "attacked": _mean(entry["attacked"]),
            "ambiguous": _mean(entry["ambiguous"]),
            "interior_only": _mean(entry["interior_only"]),
            "windows": _mean(entry["n_windows"]),
        }
        record = {
            "label": f"{int(duration)}s",
            "n_episodes": entry["n_episodes"],
            "n_segments_without_start": entry[
                "n_segments_without_start"
            ],
            "mean_windows_per_episode": means["windows"],
            "mean_attacked_windows_per_episode": means["attacked"],
            "mean_ambiguous_windows_per_episode": means["ambiguous"],
            "mean_interior_only_windows_per_episode": means[
                "interior_only"
            ],
        }
        reference = REFERENCE_MEANS.get(duration)
        if reference is not None:
            record["reference_attacked"] = reference["attacked"]
            record["reference_interior_only"] = reference[
                "interior_only"
            ]
            if means["attacked"] is not None:
                record["difference_attacked"] = round(
                    means["attacked"] - reference["attacked"], 4
                )
            if means["interior_only"] is not None:
                record["difference_interior_only"] = round(
                    means["interior_only"] - reference["interior_only"],
                    4,
                )
        report["per_duration"][str(int(duration))] = record

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    print(
        f"Segments sampled: {len(sampled):,} of {args.segments:,} requested"
    )
    for duration in SPAN_DURATIONS:
        record = report["per_duration"][str(int(duration))]
        line = (
            f"{record['label']}: episodes {record['n_episodes']:,}; "
            f"attacked {record['mean_attacked_windows_per_episode']}; "
            f"ambiguous {record['mean_ambiguous_windows_per_episode']}; "
            f"interior-only "
            f"{record['mean_interior_only_windows_per_episode']}"
        )
        if "difference_attacked" in record:
            line += (
                f" (reference attacked {record['reference_attacked']}, "
                f"diff {record['difference_attacked']:+.2f}; "
                f"interior-only {record['reference_interior_only']}, "
                f"diff {record['difference_interior_only']:+.2f})"
            )
        print(line)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
