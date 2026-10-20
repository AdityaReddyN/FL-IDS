"""Row, pair, window-start, and replay-source eligibility for v3 episodes.

Eligibility is deliberately conservative: a row is usable only when it is
airborne, has a fresh contact, and every field whose value will be modified
*and* every field needed to measure the effect is observed (not NaN and its
``*_missing`` flag is false).

``eligible_starts`` does not decide which fields an attack needs. The caller
builds ``row_ok_mask`` as ``row_eligible(...)`` combined with any
attack-specific requirement (for replay, ``has_valid_source``). Nothing is
hidden inside the start scan.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .schemas import FEATURE_FIELDS

MAX_CONTACT_LAG_SECONDS = 30.0
MAX_PAIR_DT_SECONDS = 30.0

# Provisional attack-family field requirements (D-021). Each tuple is the union
# of the fields to modify and the fields needed to measure the effect.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "horizontal_manipulation": ("lat", "lon", "velocity", "heading"),
    "freeze": ("lat", "lon", "velocity", "heading"),
    "altitude_manipulation": ("baroaltitude", "vertrate"),
    "altitude_manipulation_baro_plus_geo": (
        "baroaltitude",
        "geoaltitude",
        "vertrate",
    ),
    "replay_partial_field": (
        "lat",
        "lon",
        "baroaltitude",
        "velocity",
        "heading",
        "vertrate",
    ),
    "replay_full_field": FEATURE_FIELDS,
}


def _bool_array(values, length: int, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.shape != (length,):
        raise ValueError(f"{name} must have shape ({length},)")
    if array.dtype != bool:
        array = array.astype(bool)
    return array


def _require_columns(df: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError("missing required column(s): " + ", ".join(missing))


def row_eligible(df: pd.DataFrame, fields: Iterable[str]) -> np.ndarray:
    """Return a boolean mask of rows usable for an attack on ``fields``.

    ``fields`` is the union of fields to modify and fields needed to measure
    the effect. A field is observed only when its value is not NaN and its
    ``{field}_missing`` flag is false.
    """
    required = tuple(dict.fromkeys(fields))
    if not required:
        raise ValueError("fields must contain at least one feature")

    unknown = [field for field in required if field not in FEATURE_FIELDS]
    if unknown:
        raise KeyError("unknown feature field(s): " + ", ".join(unknown))

    _require_columns(
        df,
        (
            "onground",
            "contact_lag_seconds",
            "contact_lag_missing",
            *required,
            *(f"{field}_missing" for field in required),
        ),
    )

    onground = df["onground"].fillna(True).astype(bool).to_numpy()
    lag_missing = (
        df["contact_lag_missing"].fillna(True).astype(bool).to_numpy()
    )
    lag = pd.to_numeric(
        df["contact_lag_seconds"], errors="coerce"
    ).to_numpy(dtype=float)

    mask = ~onground
    mask &= ~lag_missing
    mask &= np.isfinite(lag) & (lag >= 0.0) & (lag <= MAX_CONTACT_LAG_SECONDS)

    values = df[list(required)].apply(pd.to_numeric, errors="coerce")
    observed = values.notna().to_numpy().all(axis=1)
    flags = (
        df[[f"{field}_missing" for field in required]]
        .fillna(True)
        .astype(bool)
        .to_numpy()
    )
    mask &= observed & ~flags.any(axis=1)
    return mask


def pair_valid(df: pd.DataFrame) -> np.ndarray:
    """Return a mask marking rows whose preceding row forms a valid pair.

    A valid pair stays within one ``(icao24, segment_id)`` group and has
    ``0 < dt <= 30`` seconds. The first row is always false.
    """
    _require_columns(df, ("icao24", "segment_id", "time"))
    if len(df) == 0:
        return np.zeros(0, dtype=bool)

    same_aircraft = df["icao24"] == df["icao24"].shift(1)
    same_segment = df["segment_id"] == df["segment_id"].shift(1)
    dt = pd.to_numeric(df["time"], errors="coerce") - pd.to_numeric(
        df["time"], errors="coerce"
    ).shift(1)
    valid = (
        same_aircraft
        & same_segment
        & (dt > 0)
        & (dt <= MAX_PAIR_DT_SECONDS)
    ).fillna(False)
    mask = valid.to_numpy(dtype=bool).copy()
    mask[0] = False
    return mask


def eligible_starts(
    segment_rows: pd.DataFrame,
    n_rows: int,
    row_ok_mask,
    pair_ok_mask,
) -> np.ndarray:
    """Return 0-based start offsets of valid ``n_rows`` windows in one segment.

    The window covers ``[start, start + n_rows)``; every row must pass
    ``row_ok_mask`` and every adjacent pair inside the window must pass
    ``pair_ok_mask``. ``segment_rows`` must contain exactly one
    ``(icao24, segment_id)`` group when those columns are present.
    """
    if not isinstance(n_rows, (int, np.integer)) or isinstance(n_rows, bool):
        raise TypeError("n_rows must be an integer")
    if n_rows < 1:
        raise ValueError("n_rows must be positive")

    for column in ("icao24", "segment_id"):
        if column in segment_rows.columns:
            if segment_rows[column].nunique(dropna=False) > 1:
                raise ValueError(
                    "eligible_starts expects rows from a single segment"
                )

    n = len(segment_rows)
    row_ok = _bool_array(row_ok_mask, n, "row_ok_mask")
    pair_ok = _bool_array(pair_ok_mask, n, "pair_ok_mask")
    if n_rows > n:
        return np.empty(0, dtype=np.int64)

    row_prefix = np.concatenate(([0], np.cumsum(row_ok, dtype=np.int64)))
    pair_prefix = np.concatenate(([0], np.cumsum(pair_ok, dtype=np.int64)))

    starts = np.arange(n - n_rows + 1)
    rows_count = row_prefix[starts + n_rows] - row_prefix[starts]
    pairs_count = pair_prefix[starts + n_rows] - pair_prefix[starts + 1]

    valid = (rows_count == n_rows) & (pairs_count == n_rows - 1)
    return np.flatnonzero(valid).astype(np.int64)


def replay_source_offsets(
    times,
    eligible,
    delay_s: float = 300.0,
    tolerance_s: float = 5.0,
) -> np.ndarray:
    """Return the replay source row offset for each row of one segment.

    The source is the row nearest to ``time - delay_s`` within
    ``tolerance_s``, searched over the whole segment. Ties go to the earlier
    row. ``-1`` means no usable source: no row within tolerance, the nearest
    row is the target row or a later row, or that nearest row is ineligible.
    Target-row eligibility is never consulted; the caller decides separately
    whether a target is usable.
    """
    times = np.asarray(times, dtype=np.int64)
    eligible = np.asarray(eligible, dtype=bool)

    if times.ndim != 1:
        raise ValueError("times must be one-dimensional")
    if eligible.shape != times.shape:
        raise ValueError("eligible must have the same shape as times")
    if np.any(np.diff(times) <= 0):
        raise ValueError("times must be strictly increasing (sorted)")
    if delay_s < 0:
        raise ValueError("delay_s must be non-negative")
    if tolerance_s < 0:
        raise ValueError("tolerance_s must be non-negative")

    n = times.size
    sources = np.full(n, -1, dtype=np.int64)
    if n == 0:
        return sources

    desired = times.astype(float) - float(delay_s)
    right = np.clip(np.searchsorted(times, desired, side="left"), 0, n - 1)
    left = np.clip(right - 1, 0, n - 1)

    right_distance = np.abs(times[right] - desired)
    left_distance = np.abs(times[left] - desired)
    picked = np.where(right_distance < left_distance, right, left)
    distance = np.minimum(right_distance, left_distance)

    usable = (
        (distance <= tolerance_s)
        & (picked < np.arange(n))
        & eligible[picked]
    )
    sources[usable] = picked[usable]
    return sources
