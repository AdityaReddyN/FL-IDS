"""Read-only eligibility and kinematics check on the real cleaned table.

Run this script yourself; it does not create attacks, windows, or datasets. It
writes one JSON report and prints a short summary.

It reports both the calibration convention already recorded in
``docs/PROGRESS_LOG.md`` ("calibration style") and the stricter foundation
conventions in ``flids.attacks`` (missing flags checked, pair time bounds, and
a replay lookup that is independent of target eligibility). Differences are
expected and are part of what this check is for.

Reference values (from the calibration run recorded in PROGRESS_LOG session 6):

* base eligible row share: 51.91 / 50.25 / 50.47 % (train/val/test)
* replay eligible row share: 41.44 / 39.89 / 40.39 %
* all-eligible 30-row stride-10 starts: 80,979 / 17,188 / 17,310
* replay 30-row stride-10 starts: 59,923 / 12,505 / 12,738
* train-only horizontal residual p95 (m): 491.91 / 919.12 / 1883.64 / 2505.35
  for speed bands 0_50 / 50_100 / 100_200 / 200_plus
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
    MAX_PAIR_DT_SECONDS,
    REQUIRED_FIELDS,
    eligible_starts,
    pair_valid,
    replay_source_offsets,
    row_eligible,
)
from flids.attacks.kinematics import (  # noqa: E402
    SPEED_BAND_NAMES,
    pair_residual_m,
    speed_band,
)
from flids.attacks.placement import (  # noqa: E402
    filter_starts_by_span,
    rows_for_duration,
)
from flids.attacks.schemas import FEATURE_FIELDS  # noqa: E402
from flids.attacks.splits import (  # noqa: E402
    SPLIT_NAMES,
    load_split_aircraft,
    validate_splits,
)

REFERENCE = {
    "base_eligibility_share_pct": {"train": 51.91, "val": 50.25, "test": 50.47},
    "replay_eligibility_share_pct": {"train": 41.44, "val": 39.89, "test": 40.39},
    "all_eligible_stride10_windows": {
        "train": 80_979,
        "val": 17_188,
        "test": 17_310,
    },
    "replay_stride10_windows": {
        "train": 59_923,
        "val": 12_505,
        "test": 12_738,
    },
    "train_p95_residual_m": {
        "0_50": 491.91445592729985,
        "50_100": 919.1229483725571,
        "100_200": 1883.6379529399999,
        "200_plus": 2505.3475617600006,
    },
}

WINDOW_ROWS = 30
WINDOW_STRIDE = 10
SPAN_DURATIONS = (120.0, 600.0, 900.0)

# Read-only attribution context: the human-reported train counts whose gap
# against REFERENCE this script decomposes. These are not targets and no
# eligibility or stride convention is tuned to reproduce them.
REPORTED_TRAIN_COUNTS = {
    "all_eligible_stride10": 78_211,
    "replay_stride10": 57_763,
}


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
        "--calibration",
        type=Path,
        default=Path("docs/calibration_v3_stage1.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results/eligibility_check_v3/report.json"),
    )
    return parser.parse_args()


def quantiles(values, points=(0.01, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)) -> dict:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return {"n": 0, **{f"q{int(point * 100):02d}": None for point in points},
                "min": None, "max": None}
    result = {"n": int(array.size)}
    for point in points:
        result[f"q{int(point * 100):02d}"] = float(np.quantile(array, point))
    result["min"] = float(array.min())
    result["max"] = float(array.max())
    return result


def load_train_thresholds(path: Path) -> dict[str, float]:
    if not path.exists():
        return dict(REFERENCE["train_p95_residual_m"])
    with path.open("r", encoding="utf-8") as handle:
        calibration = json.load(handle)
    train_only = calibration.get("speed_band_p95_threshold_meters", {}).get(
        "train_only", {}
    )
    thresholds = {}
    for band in SPEED_BAND_NAMES:
        if band in train_only:
            thresholds[band] = float(train_only[band])
    if len(thresholds) != len(SPEED_BAND_NAMES):
        return dict(REFERENCE["train_p95_residual_m"])
    return thresholds


def calibration_nearest_source(
    times: np.ndarray,
    eligible: np.ndarray,
    delay_s: float,
    tolerance_s: float,
) -> np.ndarray:
    """Mirror of scripts/calibrate_v3_stage1.py ``replay_links`` (eligible pool)."""
    result = np.full(times.size, -1, dtype=np.int64)
    source_positions = np.flatnonzero(eligible)
    if source_positions.size == 0:
        return result

    source_times = times[source_positions].astype(float)
    desired = times.astype(float) - delay_s
    right = np.searchsorted(source_times, desired, side="left")
    left = np.clip(right - 1, 0, source_positions.size - 1)
    right = np.clip(right, 0, source_positions.size - 1)
    right_distance = np.abs(source_times[right] - desired)
    left_distance = np.abs(source_times[left] - desired)
    picked = np.where(right_distance < left_distance, right, left)
    distance = np.minimum(right_distance, left_distance)
    valid = (distance <= tolerance_s) & (source_times[picked] < times)
    result[valid] = source_positions[picked[valid]]
    return result


def split_breakdown(mask: np.ndarray, split_arr: np.ndarray) -> dict:
    total = {}
    for name in SPLIT_NAMES:
        in_split = split_arr == name
        n_rows = int(in_split.sum())
        n_true = int((mask & in_split).sum())
        total[name] = {
            "n_rows": n_rows,
            "n_true": n_true,
            "share_pct": round(100.0 * n_true / n_rows, 4) if n_rows else None,
        }
    return total


def stride_filter(starts: np.ndarray, stride: int) -> np.ndarray:
    if stride <= 1 or starts.size == 0:
        return starts
    return starts[(starts % stride) == 0]


def whole_table_windows(
    row_mask: np.ndarray,
    split_arr: np.ndarray,
    group_boundary: np.ndarray,
    window_rows: int,
    stride: int,
) -> dict:
    """Count fully eligible windows without requiring one segment per window.

    This is the "windows may cross segment boundaries" convention. Counts are
    attributed to the split of the window's first row; crossing windows can
    therefore span aircraft or splits. The stride convention here is the
    global absolute row index modulo ``stride``.
    """
    n = row_mask.size
    result = {
        split: {
            "all_starts": 0,
            "stride10_starts": 0,
            "within_segment_all_starts": 0,
            "crossing_all_starts": 0,
            "within_segment_stride10": 0,
            "crossing_stride10": 0,
        }
        for split in SPLIT_NAMES
    }
    if n < window_rows:
        return result

    prefix = np.concatenate(([0], np.cumsum(row_mask, dtype=np.int64)))
    starts = np.arange(n - window_rows + 1)
    fully_eligible = (
        prefix[starts + window_rows] - prefix[starts]
    ) == window_rows
    valid = starts[fully_eligible]
    if valid.size == 0:
        return result

    boundary_prefix = np.concatenate(
        ([0], np.cumsum(group_boundary, dtype=np.int64))
    )
    crosses = (
        boundary_prefix[valid + window_rows]
        - boundary_prefix[valid + 1]
    ) > 0
    valid_stride = valid[(valid % stride) == 0]
    crosses_stride = (
        boundary_prefix[valid_stride + window_rows]
        - boundary_prefix[valid_stride + 1]
    ) > 0

    for split in SPLIT_NAMES:
        in_split = split_arr[valid] == split
        in_split_stride = split_arr[valid_stride] == split
        result[split] = {
            "all_starts": int(in_split.sum()),
            "stride10_starts": int(in_split_stride.sum()),
            "within_segment_all_starts": int((in_split & ~crosses).sum()),
            "crossing_all_starts": int((in_split & crosses).sum()),
            "within_segment_stride10": int(
                (in_split_stride & ~crosses_stride).sum()
            ),
            "crossing_stride10": int(
                (in_split_stride & crosses_stride).sum()
            ),
        }
    return result


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
        missing = sorted(
            df.loc[split_series.isna(), "icao24"].unique().tolist()
        )[:3]
        raise ValueError(f"aircraft missing from split file, e.g. {missing}")
    split_arr = split_series.to_numpy(dtype=object)

    n = len(df)
    time_arr = df["time"].to_numpy(dtype=np.int64)
    lat = df["lat"].to_numpy(dtype=float)
    lon = df["lon"].to_numpy(dtype=float)
    velocity = df["velocity"].to_numpy(dtype=float)
    heading = df["heading"].to_numpy(dtype=float)
    lag = df["contact_lag_seconds"].to_numpy(dtype=float)
    onground = df["onground"].fillna(False).astype(bool).to_numpy()
    icao_arr = df["icao24"].to_numpy(dtype=object)
    segment_arr = df["segment_id"].to_numpy()

    # --- Calibration-style and strict eligibility -------------------------
    calibration_observed = df[list(FEATURE_FIELDS)].notna().all(axis=1).to_numpy()
    calibration_base = (
        ~onground
        & np.isfinite(lag)
        & (lag >= 0.0)
        & (lag <= 30.0)
        & calibration_observed
    )
    strict_full = row_eligible(df, REQUIRED_FIELDS["replay_full_field"])
    strict_horizontal = row_eligible(
        df, REQUIRED_FIELDS["horizontal_manipulation"]
    )
    strict_altitude = row_eligible(
        df, REQUIRED_FIELDS["altitude_manipulation_baro_plus_geo"]
    )
    flags_any_missing = (
        df[[f"{field}_missing" for field in FEATURE_FIELDS]]
        .fillna(True)
        .astype(bool)
        .to_numpy()
        .any(axis=1)
    )

    eligibility = {
        "calibration_style": split_breakdown(calibration_base, split_arr),
        "strict_replay_full_field": split_breakdown(strict_full, split_arr),
        "strict_horizontal_manipulation": split_breakdown(
            strict_horizontal, split_arr
        ),
        "strict_altitude_manipulation": split_breakdown(
            strict_altitude, split_arr
        ),
    }
    for name in SPLIT_NAMES:
        entry = eligibility["calibration_style"][name]
        entry["reference_pct"] = REFERENCE["base_eligibility_share_pct"][name]
        entry["difference_pct"] = round(
            entry["share_pct"] - entry["reference_pct"], 4
        )

    # --- Missing flag versus NaN disagreement -----------------------------
    disagreements = {}
    for field in FEATURE_FIELDS:
        flag = (
            df[f"{field}_missing"].fillna(True).astype(bool).to_numpy()
        )
        value_nan = df[field].isna().to_numpy()
        mismatch = flag != value_nan
        disagreements[field] = split_breakdown(mismatch, split_arr)

    # --- Pairs, dt, and horizontal residuals ------------------------------
    pair_mask = pair_valid(df)
    previous_base = np.zeros(n, dtype=bool)
    previous_base[1:] = calibration_base[:-1]
    pair_base = pair_mask & calibration_base & previous_base

    previous_lat = df["lat"].shift().to_numpy(dtype=float)
    previous_lon = df["lon"].shift().to_numpy(dtype=float)
    previous_velocity = df["velocity"].shift().to_numpy(dtype=float)
    previous_heading = df["heading"].shift().to_numpy(dtype=float)
    dt_arr = (df["time"] - df["time"].shift()).to_numpy(dtype=float)

    residual = np.full(n, np.nan, dtype=float)
    residual[pair_base] = pair_residual_m(
        previous_lat[pair_base],
        previous_lon[pair_base],
        lat[pair_base],
        lon[pair_base],
        previous_velocity[pair_base],
        previous_heading[pair_base],
        dt_arr[pair_base],
    )
    raw_dlon = lon - previous_lon
    antimeridian_pairs = int(
        (np.abs(raw_dlon[pair_base]) > 180.0).sum()
    )
    nonzero_dlon = raw_dlon[pair_base][np.isfinite(raw_dlon[pair_base])]

    band_arr = speed_band(velocity)
    residuals = {}
    thresholds = load_train_thresholds(args.calibration)
    for band in SPEED_BAND_NAMES:
        by_split = {}
        for name in SPLIT_NAMES:
            mask = (
                pair_base
                & (band_arr == band)
                & (split_arr == name)
            )
            by_split[name] = quantiles(residual[mask])
        train_p95 = by_split["train"]["q95"]
        reference_p95 = thresholds[band]
        residuals[band] = {
            "by_split": by_split,
            "calibration_train_p95_m": reference_p95,
            "train_p95_ratio": (
                round(train_p95 / reference_p95, 6)
                if train_p95 is not None
                else None
            ),
        }

    # --- Replay source availability ---------------------------------------
    group_items = [
        (key, np.asarray(indices, dtype=np.int64))
        for key, indices in df.groupby(
            ["icao24", "segment_id"], sort=False
        ).indices.items()
    ]

    calibration_source = np.full(n, -1, dtype=np.int64)
    foundation_source = np.full(n, -1, dtype=np.int64)
    non_increasing_segments = 0
    for (_icao24, _segment_id), positions in group_items:
        times = time_arr[positions]
        eligible = calibration_base[positions]
        calibration_source[positions] = calibration_nearest_source(
            times, eligible, 300.0, 5.0
        )
        if np.any(np.diff(times) <= 0):
            non_increasing_segments += 1
            continue
        foundation_source[positions] = replay_source_offsets(
            times, strict_full[positions], delay_s=300.0, tolerance_s=5.0
        )

    calibration_replay_targets = (
        calibration_base & (calibration_source >= 0)
    )
    foundation_replay_targets = (
        strict_full & (foundation_source >= 0)
    )
    replay = {
        "calibration_style_targets": split_breakdown(
            calibration_replay_targets, split_arr
        ),
        "foundation_targets": split_breakdown(
            foundation_replay_targets, split_arr
        ),
        "source_available_for_any_target": split_breakdown(
            calibration_source >= 0, split_arr
        ),
        "non_increasing_segments": non_increasing_segments,
    }
    for name in SPLIT_NAMES:
        entry = replay["calibration_style_targets"][name]
        entry["reference_pct"] = REFERENCE["replay_eligibility_share_pct"][name]
        entry["difference_pct"] = round(
            entry["share_pct"] - entry["reference_pct"], 4
        )

    # --- 30-row stride-10 starts, several masks ---------------------------
    window_masks = {
        "calibration_base_rows_only": (calibration_base, None),
        "calibration_base_rows_and_pairs": (calibration_base, pair_mask),
        "calibration_replay_rows_only": (calibration_replay_targets, None),
        "foundation_strict_rows_and_pairs": (strict_full, pair_mask),
        "foundation_replay_rows_and_pairs": (
            foundation_replay_targets,
            pair_mask,
        ),
        "nan_only_rows_only": (calibration_observed, None),
        "nan_plus_flags_rows_only": (
            calibration_observed & ~flags_any_missing,
            None,
        ),
    }
    window_counts = {
        name: {
            "all_starts": {split: 0 for split in SPLIT_NAMES},
            "stride10_starts": {split: 0 for split in SPLIT_NAMES},
        }
        for name in window_masks
    }
    # Extra read-only convention counters for the reported ~3.5% gap.
    stride_attribution = {
        name: {
            split: {
                "all_starts": 0,
                "offset_mod10": 0,
                "enumerated_stride10": 0,
                "global_index_mod10": 0,
            }
            for split in SPLIT_NAMES
        }
        for name in window_masks
    }
    for key, positions in group_items:
        n_segment = positions.size
        if n_segment < WINDOW_ROWS:
            continue
        split = str(split_arr[positions[0]])
        view = _SingleSegmentRows(key[0], key[1], n_segment)
        for name, (row_mask, pair_mask_choice) in window_masks.items():
            pairs = (
                np.ones(n_segment, dtype=bool)
                if pair_mask_choice is None
                else pair_mask_choice[positions]
            )
            starts = eligible_starts(view, WINDOW_ROWS, row_mask[positions], pairs)
            window_counts[name]["all_starts"][split] += int(starts.size)
            window_counts[name]["stride10_starts"][split] += int(
                stride_filter(starts, WINDOW_STRIDE).size
            )
            attribution = stride_attribution[name][split]
            attribution["all_starts"] += int(starts.size)
            attribution["offset_mod10"] += int(
                np.count_nonzero(starts % WINDOW_STRIDE == 0)
            )
            attribution["enumerated_stride10"] += int(
                starts[::WINDOW_STRIDE].size
            )
            absolute_starts = positions[starts]
            attribution["global_index_mod10"] += int(
                np.count_nonzero(absolute_starts % WINDOW_STRIDE == 0)
            )

    for name in SPLIT_NAMES:
        entry = window_counts["calibration_base_rows_only"]["stride10_starts"]
        entry[f"reference_{name}"] = REFERENCE["all_eligible_stride10_windows"][name]
        entry[f"difference_{name}"] = (
            entry[name] - REFERENCE["all_eligible_stride10_windows"][name]
        )
    for name in SPLIT_NAMES:
        entry = window_counts["calibration_replay_rows_only"]["stride10_starts"]
        entry[f"reference_{name}"] = REFERENCE["replay_stride10_windows"][name]
        entry[f"difference_{name}"] = (
            entry[name] - REFERENCE["replay_stride10_windows"][name]
        )

    # --- Window-capacity attribution (read-only; no tuning) ---------------
    group_boundary = np.zeros(n, dtype=bool)
    group_boundary[1:] = (icao_arr[1:] != icao_arr[:-1]) | (
        segment_arr[1:] != segment_arr[:-1]
    )
    cross_boundary = {
        "calibration_base_rows_only": whole_table_windows(
            calibration_base,
            split_arr,
            group_boundary,
            WINDOW_ROWS,
            WINDOW_STRIDE,
        ),
        "calibration_replay_rows_only": whole_table_windows(
            calibration_replay_targets,
            split_arr,
            group_boundary,
            WINDOW_ROWS,
            WINDOW_STRIDE,
        ),
        "nan_only_rows_only": whole_table_windows(
            calibration_observed,
            split_arr,
            group_boundary,
            WINDOW_ROWS,
            WINDOW_STRIDE,
        ),
    }

    attribution_report = {}
    for name, reference_key in (
        ("calibration_base_rows_only", "all_eligible_stride10_windows"),
        ("calibration_replay_rows_only", "replay_stride10_windows"),
    ):
        attribution_report[name] = {}
        for split in SPLIT_NAMES:
            entry = dict(stride_attribution[name][split])
            reference = REFERENCE[reference_key][split]
            entry["reference_stride10"] = reference
            entry["offset_mod10_minus_reference"] = (
                entry["offset_mod10"] - reference
            )
            entry["enumerated_minus_offset"] = (
                entry["enumerated_stride10"] - entry["offset_mod10"]
            )
            entry["global_index_minus_offset"] = (
                entry["global_index_mod10"] - entry["offset_mod10"]
            )
            entry["all_starts_minus_offset"] = (
                entry["all_starts"] - entry["offset_mod10"]
            )
            attribution_report[name][split] = entry

    attribution_report["reported_train_counts"] = REPORTED_TRAIN_COUNTS
    attribution_report["reported_train_reference"] = {
        "all_eligible_stride10": (
            REFERENCE["all_eligible_stride10_windows"]["train"]
        ),
        "replay_stride10": REFERENCE["replay_stride10_windows"]["train"],
    }
    attribution_report["cross_segment_boundary_windows"] = cross_boundary
    attribution_report["row_mask_variants_offset_mod10"] = {
        name: {
            split: stride_attribution[name][split]["offset_mod10"]
            for split in SPLIT_NAMES
        }
        for name in (
            "nan_only_rows_only",
            "nan_plus_flags_rows_only",
            "calibration_base_rows_only",
            "foundation_strict_rows_and_pairs",
        )
    }

    # --- Span filter removals by duration --------------------------------
    span_report = {}
    for duration in SPAN_DURATIONS:
        n_rows = rows_for_duration(duration)
        label = f"{int(duration)}s"
        span_report[label] = {
            split: {
                "n_rows": n_rows,
                "segments_too_short": 0,
                "candidate_starts": 0,
                "kept_after_span": 0,
                "span_removed": 0,
            }
            for split in SPLIT_NAMES
        }
        for key, positions in group_items:
            split = str(split_arr[positions[0]])
            n_segment = positions.size
            if n_segment < n_rows:
                span_report[label][split]["segments_too_short"] += 1
                continue
            view = _SingleSegmentRows(key[0], key[1], n_segment)
            starts = eligible_starts(
                view,
                n_rows,
                strict_full[positions],
                pair_mask[positions],
            )
            kept, removed = filter_starts_by_span(
                starts, time_arr[positions], n_rows, duration
            )
            span_report[label][split]["candidate_starts"] += int(starts.size)
            span_report[label][split]["kept_after_span"] += int(kept.size)
            span_report[label][split]["span_removed"] += int(removed)

    # --- dt distribution for adjacent same-segment rows ------------------
    same_group = np.zeros(n, dtype=bool)
    same_group[1:] = (icao_arr[1:] == icao_arr[:-1]) & (
        segment_arr[1:] == segment_arr[:-1]
    )
    adjacent = same_group & np.isfinite(dt_arr)
    dt_report = {"overall": quantiles(dt_arr[adjacent])}
    for name in SPLIT_NAMES:
        mask = adjacent & (split_arr == name)
        values = dt_arr[mask]
        report = quantiles(values)
        if values.size:
            report["share_dt_eq_10"] = float((values == 10.0).mean())
            report["share_dt_ne_10"] = float((values != 10.0).mean())
            report["share_dt_le_0"] = float((values <= 0.0).mean())
            report["share_dt_gt_30"] = float((values > 30.0).mean())
            report["share_pair_valid"] = float(
                ((values > 0.0) & (values <= MAX_PAIR_DT_SECONDS)).mean()
            )
        else:
            report.update(
                {
                    "share_dt_eq_10": None,
                    "share_dt_ne_10": None,
                    "share_dt_le_0": None,
                    "share_dt_gt_30": None,
                    "share_pair_valid": None,
                }
            )
        dt_report[name] = report

    report = {
        "parameters": {
            "input": str(args.input),
            "splits": str(args.splits),
            "calibration": str(args.calibration),
            "window_rows": WINDOW_ROWS,
            "window_stride": WINDOW_STRIDE,
            "span_durations_seconds": list(SPAN_DURATIONS),
            "replay_delay_seconds": 300.0,
            "replay_tolerance_seconds": 5.0,
            "max_pair_dt_seconds": MAX_PAIR_DT_SECONDS,
        },
        "reference": REFERENCE,
        "rows_total": int(n),
        "aircraft_total": int(df["icao24"].nunique()),
        "segments_total": int(len(group_items)),
        "eligibility": eligibility,
        "missing_flag_vs_nan_disagreement": disagreements,
        "replay": replay,
        "windows": window_counts,
        "window_capacity_attribution": attribution_report,
        "span_filter": span_report,
        "dt_adjacent_pairs": dt_report,
        "horizontal_residual": {
            "antimeridian_pairs_abs_dlon_gt_180": antimeridian_pairs,
            "n_pairs": int(pair_base.sum()),
            "raw_dlon_min": (
                float(np.min(nonzero_dlon)) if nonzero_dlon.size else None
            ),
            "raw_dlon_max": (
                float(np.max(nonzero_dlon)) if nonzero_dlon.size else None
            ),
            "by_speed_band": residuals,
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    print(f"Rows={n:,}; aircraft={report['aircraft_total']:,}; segments={len(group_items):,}")
    print("Eligibility (calibration style):")
    for name in SPLIT_NAMES:
        entry = eligibility["calibration_style"][name]
        print(
            f"  {name}: {entry['share_pct']:.2f}% "
            f"(reference {entry['reference_pct']:.2f}%)"
        )
    print("Replay targets (calibration style):")
    for name in SPLIT_NAMES:
        entry = replay["calibration_style_targets"][name]
        print(
            f"  {name}: {entry['share_pct']:.2f}% "
            f"(reference {entry['reference_pct']:.2f}%); "
            f"foundation {replay['foundation_targets'][name]['share_pct']:.2f}%"
        )
    print("30-row stride-10 starts:")
    base_entry = window_counts["calibration_base_rows_only"]["stride10_starts"]
    replay_entry = window_counts["calibration_replay_rows_only"][
        "stride10_starts"
    ]
    for name in SPLIT_NAMES:
        print(
            f"  {name}: base {base_entry[name]:,} "
            f"(ref {base_entry[f'reference_{name}']:,}); "
            f"replay {replay_entry[name]:,} "
            f"(ref {replay_entry[f'reference_{name}']:,})"
        )
    print("Window-capacity attribution (reported train gap 2,768 / 2,160):")
    for label, key in (
        ("base", "calibration_base_rows_only"),
        ("replay", "calibration_replay_rows_only"),
    ):
        entry = attribution_report[key]["train"]
        print(
            f"  {label}: offset-mod {entry['offset_mod10']:,} "
            f"(ref {entry['reference_stride10']:,}; "
            f"delta {entry['offset_mod10_minus_reference']:+,}); "
            f"enumerated {entry['enumerated_stride10']:,} "
            f"({entry['enumerated_minus_offset']:+,}); "
            f"global-index {entry['global_index_mod10']:,} "
            f"({entry['global_index_minus_offset']:+,})"
        )
    print("Fully eligible windows crossing segment boundaries (train):")
    for label, key in (
        ("base", "calibration_base_rows_only"),
        ("replay", "calibration_replay_rows_only"),
        ("nan-only", "nan_only_rows_only"),
    ):
        entry = cross_boundary[key]["train"]
        print(
            f"  {label}: within-segment {entry['within_segment_all_starts']:,} "
            f"+ crossing {entry['crossing_all_starts']:,} "
            f"= {entry['all_starts']:,}; stride10 within "
            f"{entry['within_segment_stride10']:,} + crossing "
            f"{entry['crossing_stride10']:,}"
        )
    print("Row-mask variants (train, stride-10 offset-mod):")
    for label, key in (
        ("nan-only", "nan_only_rows_only"),
        ("nan+flags", "nan_plus_flags_rows_only"),
        ("calibration-base", "calibration_base_rows_only"),
        ("strict full", "foundation_strict_rows_and_pairs"),
    ):
        value = attribution_report["row_mask_variants_offset_mod10"][key][
            "train"
        ]
        print(f"  {label}: {value:,}")
    print(
        "Pairs with |dlon|>180: "
        f"{antimeridian_pairs:,} of {int(pair_base.sum()):,}"
    )
    for band in SPEED_BAND_NAMES:
        entry = residuals[band]
        observed = entry["by_split"]["train"]["q95"]
        print(
            f"  residual p95 {band}: train {observed:.2f} m "
            f"vs calibration {entry['calibration_train_p95_m']:.2f} m "
            f"(ratio {entry['train_p95_ratio']})"
        )
    print("Adjacent-pair dt overall:", dt_report["overall"])
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
