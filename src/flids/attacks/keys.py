"""Natural keys for the cleaned row table.

``source_row_id`` is the row position in the cleaned table at read time.
``segment_row_offset`` is the 0-based position of the row within its
``(icao24, segment_id)`` group ordered by ``time`` (stable mergesort).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

GROUP_COLUMNS: tuple[str, str] = ("icao24", "segment_id")
SOURCE_KEY_COLUMNS: tuple[str, str, str] = ("icao24", "segment_id", "time")
KEY_COLUMNS: tuple[str, str, str, str] = (
    "icao24",
    "segment_id",
    "time",
    "segment_row_offset",
)


class NaturalKeyError(ValueError):
    """Raised when natural-key columns are missing, duplicated, or invalid."""


def _require_columns(df: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise NaturalKeyError(
            "missing required column(s): " + ", ".join(sorted(missing))
        )


def _duplicate_count(df: pd.DataFrame, columns: tuple[str, ...]) -> int:
    return int(df.duplicated(subset=list(columns), keep="first").sum())


def add_natural_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with ``source_row_id`` and ``segment_row_offset`` added.

    ``source_row_id`` preserves the input row order. ``segment_row_offset`` is
    assigned after a stable sort by ``(icao24, segment_id, time)``, so the
    original position breaks any ties deterministically.
    """
    _require_columns(df, SOURCE_KEY_COLUMNS)

    out = df.copy().reset_index(drop=True)
    out["source_row_id"] = np.arange(len(out), dtype=np.int64)

    duplicates = _duplicate_count(out, SOURCE_KEY_COLUMNS)
    if duplicates:
        raise NaturalKeyError(
            f"found {duplicates} duplicate (icao24, segment_id, time) row(s); "
            "refusing to assign ambiguous segment_row_offset values"
        )

    order = out.sort_values(
        list(SOURCE_KEY_COLUMNS), kind="mergesort"
    ).index.to_numpy()
    sorted_offsets = (
        out.iloc[order]
        .groupby(list(GROUP_COLUMNS), sort=False)
        .cumcount()
        .to_numpy(dtype=np.int32)
    )

    segment_row_offset = np.empty(len(out), dtype=np.int32)
    segment_row_offset[order] = sorted_offsets
    out["segment_row_offset"] = segment_row_offset
    return out


def assert_natural_key_unique(df: pd.DataFrame) -> None:
    """Raise :class:`NaturalKeyError` if the full natural key is not unique."""
    _require_columns(df, KEY_COLUMNS)
    duplicates = _duplicate_count(df, KEY_COLUMNS)
    if duplicates:
        raise NaturalKeyError(f"found {duplicates} duplicate natural key row(s)")
