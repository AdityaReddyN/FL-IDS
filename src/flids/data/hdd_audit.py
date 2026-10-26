"""Pure helpers for the read-only HDD source audit (S3).

None of these functions read files, process, resample, or attack HDD data. They
compute the per-archive statistics the audit reports and are unit-tested on tiny
synthetic arrays. The orchestration (streaming the tar archives, writing JSON)
lives in ``scripts/audit_hdd_source.py``.

Candidate resampling to 10 s is *estimated* here (how many rows would remain),
never applied: the resampling rule is a human decision for Stage S4.
"""

from __future__ import annotations

import numpy as np

# The cleaned-table contract (see scripts/build_dataset.py): the HDD source must
# supply these before it can feed the existing pipeline.
EXPECTED_COLUMNS: tuple[str, ...] = (
    "time", "icao24", "lat", "lon", "velocity", "heading", "vertrate",
    "onground", "baroaltitude", "geoaltitude", "lastcontact",
)

_DT_QUANTILE_POINTS: tuple[float, ...] = (0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99)


def column_schema_diff(columns) -> dict:
    """Compare observed columns against :data:`EXPECTED_COLUMNS`."""
    observed = [str(name).strip() for name in columns]
    observed_set = set(observed)
    expected_set = set(EXPECTED_COLUMNS)
    return {
        "observed": observed,
        "missing_required": sorted(expected_set - observed_set),
        "extra": sorted(observed_set - expected_set),
        "matches_contract": expected_set.issubset(observed_set),
    }


def _finite(values) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return array[np.isfinite(array)]


def dt_quantiles(times, points: tuple[float, ...] = _DT_QUANTILE_POINTS) -> dict:
    """Quantiles of consecutive time differences within a single sorted track.

    ``times`` is one aircraft track's timestamps (seconds). Non-increasing steps
    are kept (they are a finding), but NaNs are dropped.
    """
    time_values = np.asarray(times, dtype=float)
    if time_values.size < 2:
        return {"n_steps": 0, **{f"p{int(p * 100):02d}": None for p in points}}
    dt = _finite(np.diff(time_values))
    if dt.size == 0:
        return {"n_steps": 0, **{f"p{int(p * 100):02d}": None for p in points}}
    out = {"n_steps": int(dt.size)}
    for point in points:
        out[f"p{int(point * 100):02d}"] = float(np.quantile(dt, point))
    return out


def cadence_shares(dt, gap_seconds: float = 30.0) -> dict:
    """Shares of consecutive dt values that are exactly 1 s, exactly 10 s, >gap."""
    values = _finite(dt)
    if values.size == 0:
        return {"n_steps": 0, "share_dt_eq_1s": None, "share_dt_eq_10s": None,
                "share_dt_gt_gap": None, "gap_seconds": gap_seconds}
    return {
        "n_steps": int(values.size),
        "share_dt_eq_1s": float(np.mean(values == 1.0)),
        "share_dt_eq_10s": float(np.mean(values == 10.0)),
        "share_dt_gt_gap": float(np.mean(values > gap_seconds)),
        "gap_seconds": gap_seconds,
    }


def aircraft_recurrence(per_bucket_aircraft) -> dict:
    """Aircraft recurrence across buckets (hours or dates).

    ``per_bucket_aircraft`` maps a bucket label to an iterable of ``icao24``.
    Reports how many aircraft appear in more than one bucket, which is the
    split-leakage risk if the split is not global by aircraft.
    """
    buckets = {str(label): set(map(str, members)) for label, members in dict(per_bucket_aircraft).items()}
    counts: dict[str, int] = {}
    for members in buckets.values():
        for icao in members:
            counts[icao] = counts.get(icao, 0) + 1
    unique = set(counts)
    recurring = {icao for icao, n in counts.items() if n > 1}
    return {
        "n_buckets": len(buckets),
        "unique_aircraft": len(unique),
        "aircraft_in_multiple_buckets": len(recurring),
        "max_buckets_for_one_aircraft": max(counts.values()) if counts else 0,
        "recurrence_share": (len(recurring) / len(unique)) if unique else None,
    }


def cell_coverage(lat, lon, degrees: float = 5.0) -> dict:
    """Lat/lon bounding box and the set of occupied ``degrees``-sized cells."""
    lat_values = _finite(lat)
    lon_values = _finite(lon)
    if lat_values.size == 0 or lon_values.size == 0:
        return {"n_points": 0, "lat_min": None, "lat_max": None,
                "lon_min": None, "lon_max": None, "n_cells": 0}
    n = min(lat_values.size, lon_values.size)
    lat_cells = np.floor((lat_values[:n] + 90.0) / degrees).astype(np.int64)
    lon_cells = np.floor((lon_values[:n] + 180.0) / degrees).astype(np.int64)
    cells = {f"{int(a)}:{int(b)}" for a, b in zip(lat_cells, lon_cells)}
    return {
        "n_points": int(n),
        "lat_min": float(lat_values.min()), "lat_max": float(lat_values.max()),
        "lon_min": float(lon_values.min()), "lon_max": float(lon_values.max()),
        "degrees": degrees, "n_cells": len(cells),
    }


def resample_count_estimate(times, rule: str = "decimate_mod10") -> dict:
    """Estimate rows remaining after a candidate 10 s resampling of one track.

    ``decimate_mod10`` keeps rows whose integer second is a multiple of 10.
    ``nearest_10s`` keeps one row per distinct 10 s bucket (``floor(t/10)``).
    Neither is applied to any data; this only sizes the compute budget.
    """
    time_values = _finite(times)
    original = int(time_values.size)
    if original == 0:
        return {"rule": rule, "original_rows": 0, "estimated_rows": 0, "reduction_ratio": None}
    if rule == "decimate_mod10":
        kept = int(np.count_nonzero(np.mod(np.round(time_values).astype(np.int64), 10) == 0))
    elif rule == "nearest_10s":
        kept = int(np.unique(np.floor(time_values / 10.0).astype(np.int64)).size)
    else:
        raise ValueError(f"unknown resampling rule: {rule!r}")
    return {
        "rule": rule, "original_rows": original, "estimated_rows": kept,
        "reduction_ratio": kept / original,
    }
