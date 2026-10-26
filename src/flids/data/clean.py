"""Shared cleaning for OpenSky state-vector tables (v1 and HDD).

This is the single source of truth for the cleaned-table conventions used by
``scripts/build_dataset.py`` (the 2-hour 2017 slice) and
``scripts/build_hdd_dataset.py`` (the HDD source). Both produce a table with the
exact ``opensky_clean_v1`` schema and column order.

Conventions (see ``docs/PROJECT_CONTEXT.md`` and ``AGENTS.md``):
- rows with a missing ``time`` or ``icao24`` are dropped;
- ``{feature}_missing`` int8 flags for the seven continuous features only;
- ``heading_sin``/``heading_cos`` from the heading in degrees;
- ``contact_lag_seconds = time - lastcontact`` with a ``contact_lag_missing`` flag;
- ``segment_id`` increments per aircraft whenever the gap to the previous row
  exceeds ``segment_gap_seconds`` (default 30 s). Cleaning never edits feature
  values (e.g. velocity glitches are preserved, not clipped); plausibility is an
  eligibility/attack-time concern, not a cleaning concern.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES: tuple[str, ...] = (
    "lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude",
)
# Columns read from a raw state-vector source before cleaning.
RAW_COLUMNS: tuple[str, ...] = ("time", "icao24", "onground", *FEATURES, "lastcontact")

# Canonical output column order (equals opensky_clean_v1).
CLEAN_COLUMNS: tuple[str, ...] = (
    "time", "icao24", *FEATURES, "onground", "lastcontact",
    *(f"{name}_missing" for name in FEATURES),
    "heading_sin", "heading_cos", "contact_lag_seconds", "contact_lag_missing",
    "segment_id",
)

DEFAULT_SEGMENT_GAP_SECONDS = 30.0


def normalize_raw(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce a raw source frame to numeric types and drop unusable rows.

    Keeps the :data:`RAW_COLUMNS` (those present), strips column names, coerces
    ``time`` and the continuous columns to numeric, drops rows missing ``time``
    or ``icao24``, and normalizes ``icao24`` to a lowercase string.
    """
    frame = frame.copy()
    frame.columns = [str(c).strip() for c in frame.columns]
    present = [c for c in RAW_COLUMNS if c in frame.columns]
    frame = frame[present]
    frame["time"] = pd.to_numeric(frame["time"], errors="coerce")
    for col in (*FEATURES, "lastcontact"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["time", "icao24"]).copy()
    frame["icao24"] = frame["icao24"].astype(str).str.strip().str.lower()
    frame["time"] = frame["time"].astype(np.int64)
    return frame


def _coerce_onground(series: pd.Series) -> pd.Series:
    """Return a boolean (nullable only if the source has nulls) onground column."""
    if series.dtype == bool:
        return series
    mapped = (
        series.astype("string").str.strip().str.lower()
        .map({"true": True, "false": False, "1": True, "0": False})
    )
    # Fall back to pandas truthiness for already-boolean-like values.
    mapped = mapped.where(series.astype("string").str.strip().str.lower().isin(
        ["true", "false", "1", "0"]
    ), series)
    boolean = pd.array(mapped, dtype="boolean")
    return boolean.astype(bool) if not boolean.isna().any() else boolean


def finalize_clean(
    frame: pd.DataFrame,
    segment_gap_seconds: float = DEFAULT_SEGMENT_GAP_SECONDS,
) -> pd.DataFrame:
    """Add derived columns and ``segment_id`` to a normalized frame.

    The input must already be normalized (see :func:`normalize_raw`). Output is
    sorted by ``(icao24, time)`` with the canonical :data:`CLEAN_COLUMNS` order.
    Safe to call per aircraft-group / per bucket: ``segment_id`` is computed
    within each ``icao24``.
    """
    df = frame.sort_values(["icao24", "time"], kind="mergesort").reset_index(drop=True)
    for col in FEATURES:
        if col not in df.columns:
            df[col] = np.nan
        df[f"{col}_missing"] = df[col].isna().astype("int8")
    if "lastcontact" not in df.columns:
        df["lastcontact"] = np.nan
    if "onground" not in df.columns:
        df["onground"] = pd.NA
    df["onground"] = _coerce_onground(df["onground"])
    angle = np.deg2rad(df["heading"])
    df["heading_sin"] = np.sin(angle)
    df["heading_cos"] = np.cos(angle)
    df["contact_lag_seconds"] = df["time"] - df["lastcontact"]
    df["contact_lag_missing"] = df["contact_lag_seconds"].isna().astype("int8")
    gap = df.groupby("icao24", sort=False)["time"].diff()
    df["segment_id"] = (
        (gap.isna() | (gap > segment_gap_seconds))
        .groupby(df["icao24"], sort=False).cumsum().astype("int32")
    )
    for col in FEATURES + ("lastcontact",):
        df[col] = df[col].astype("float64")
    return df[list(CLEAN_COLUMNS)]


def clean_frame(
    frame: pd.DataFrame,
    segment_gap_seconds: float = DEFAULT_SEGMENT_GAP_SECONDS,
) -> pd.DataFrame:
    """Normalize and finalize a raw source frame in one call."""
    return finalize_clean(normalize_raw(frame), segment_gap_seconds)
