"""Freeze (position hold) for one episode (D-023).

Freeze blends each active row's latitude and longitude toward an anchor that
the caller supplies::

    modified = (1 - a_t) * current + a_t * anchor

Longitude blends along the shortest arc and is wrapped into ``[-180, 180)``.
Only ``lat`` and ``lon`` are ever changed: velocity, heading, vertical rate and
altitudes are not accepted by these functions. A ``None`` anchor means the
caller must reject the episode with ``reason="no_freeze_anchor"``.
"""

from __future__ import annotations

import numpy as np

from .manipulation import ManipulationResult

ACTIVE_THRESHOLD = 0.0
DEFAULT_MAX_ANCHOR_AGE_SECONDS = 30.0


def _one_dimensional(values, name: str) -> np.ndarray:
    array = np.array(values, dtype=float, copy=True)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def _multipliers(values, length: int) -> np.ndarray:
    array = _one_dimensional(values, "a")
    if array.shape != (length,):
        raise ValueError("a must have the same shape as the target arrays")
    if not np.all(np.isfinite(array)):
        raise ValueError("a must contain only finite values")
    if np.any(array < 0.0):
        raise ValueError("a must be non-negative")
    return array


def _require_finite_on_active(active, arrays: dict[str, np.ndarray]) -> None:
    for name, array in arrays.items():
        if np.any(active & ~np.isfinite(array)):
            raise ValueError(
                f"{name} contains NaN or inf on rows with a_t > 0"
            )


def _anchor_values(anchor_lat, anchor_lon) -> tuple[float, float]:
    lat = float(anchor_lat)
    lon = float(anchor_lon)
    if not np.isfinite(lat) or not np.isfinite(lon):
        raise ValueError("the anchor latitude and longitude must be finite")
    if not -90.0 <= lat <= 90.0:
        raise ValueError("the anchor latitude must be in [-90, 90]")
    return lat, lon


def freeze_lat_lon(
    lat,
    lon,
    a,
    anchor_lat: float,
    anchor_lon: float,
) -> ManipulationResult:
    """Blend active rows toward ``(anchor_lat, anchor_lon)``.

    The result carries only ``lat`` and ``lon``. Rows with ``a_t == 0`` are
    copied bit-identically. Longitude uses the shortest arc.
    """
    lat_in = _one_dimensional(lat, "lat")
    lon_in = _one_dimensional(lon, "lon")
    if lat_in.shape != lon_in.shape:
        raise ValueError("lat and lon must have the same shape")
    multipliers = _multipliers(a, lat_in.size)
    anchor_lat_value, anchor_lon_value = _anchor_values(
        anchor_lat, anchor_lon
    )

    active = multipliers > ACTIVE_THRESHOLD
    _require_finite_on_active(
        active, {"lat": lat_in, "lon": lon_in}
    )

    lat_out = lat_in.copy()
    lon_out = lon_in.copy()
    if np.any(active):
        current = multipliers[active]
        lat_out[active] = (
            (1.0 - current) * lat_in[active]
            + current * anchor_lat_value
        )
        delta = (
            anchor_lon_value - lon_in[active] + 180.0
        ) % 360.0 - 180.0
        blended = lon_in[active] + current * delta
        wrapped = (blended + 180.0) % 360.0 - 180.0
        lon_out[active] = np.where(wrapped >= 180.0, -180.0, wrapped)

    return ManipulationResult(
        values={"lat": lat_out, "lon": lon_out},
        multipliers=multipliers,
    )


def anchor_from_offsets(
    lat,
    lon,
    eligible_mask,
    start_offset: int,
    times,
    max_anchor_age_seconds: float = DEFAULT_MAX_ANCHOR_AGE_SECONDS,
):
    """Return the last fully eligible lat/lon strictly before ``start_offset``.

    The anchor is the highest offset ``k < start_offset`` whose
    ``eligible_mask[k]`` is true and whose latitude and longitude are finite.
    The anchor age ``times[start_offset] - times[k]`` must be at most
    ``max_anchor_age_seconds``; otherwise there is no usable anchor and the
    function returns ``None`` (the caller rejects with
    ``"no_freeze_anchor"``). The start row itself is never used.
    """
    lat_in = _one_dimensional(lat, "lat")
    lon_in = _one_dimensional(lon, "lon")
    if lat_in.shape != lon_in.shape:
        raise ValueError("lat and lon must have the same shape")

    eligible = np.asarray(eligible_mask)
    if eligible.shape != lat_in.shape:
        raise ValueError("eligible_mask must have the same shape as lat")
    eligible = eligible.astype(bool, copy=False)

    time_values = _one_dimensional(times, "times")
    if time_values.shape != lat_in.shape:
        raise ValueError("times must have the same shape as lat")

    n_rows = lat_in.size
    if (
        not isinstance(start_offset, (int, np.integer))
        or isinstance(start_offset, bool)
    ):
        raise TypeError("start_offset must be an integer")
    if start_offset < 0 or start_offset >= n_rows:
        raise ValueError("start_offset must be a valid row offset")

    max_age = float(max_anchor_age_seconds)
    if not np.isfinite(max_age) or max_age < 0.0:
        raise ValueError(
            "max_anchor_age_seconds must be finite and non-negative"
        )

    for offset in range(start_offset - 1, -1, -1):
        if not eligible[offset]:
            continue
        if not np.isfinite(lat_in[offset]) or not np.isfinite(
            lon_in[offset]
        ):
            continue
        age = time_values[start_offset] - time_values[offset]
        if age <= max_age:
            return float(lat_in[offset]), float(lon_in[offset])
        # Earlier eligible rows are older, so no anchor can satisfy the limit.
        return None
    return None
