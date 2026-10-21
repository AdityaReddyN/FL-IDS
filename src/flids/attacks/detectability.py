"""Detectability reporting helpers (D-023).

These are pure functions used later to build reporting strata. They do not
decide window labels.
"""

from __future__ import annotations

import numpy as np

from .kinematics import METRES_PER_DEGREE, pair_residual_m


def _one_dimensional(values, name: str) -> np.ndarray:
    array = np.array(values, dtype=float, copy=True)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def residual_series(lat, lon, velocity, heading, time) -> np.ndarray:
    """Return the horizontal pair residual for each adjacent row pair.

    Element ``k`` covers the pair ``(k - 1, k)`` and uses the velocity and
    heading of row ``k - 1`` (the earlier row), matching the calibration
    script; element 0 is always ``NaN``. ``dt`` is ``time[k] - time[k - 1]``.
    """
    lat_in = _one_dimensional(lat, "lat")
    lon_in = _one_dimensional(lon, "lon")
    velocity_in = _one_dimensional(velocity, "velocity")
    heading_in = _one_dimensional(heading, "heading")
    time_in = _one_dimensional(time, "time")
    for name, array in (
        ("lon", lon_in),
        ("velocity", velocity_in),
        ("heading", heading_in),
        ("time", time_in),
    ):
        if array.shape != lat_in.shape:
            raise ValueError(f"{name} must have the same shape as lat")

    residual = np.full(lat_in.size, np.nan)
    if lat_in.size > 1:
        residual[1:] = pair_residual_m(
            lat_in[:-1],
            lon_in[:-1],
            lat_in[1:],
            lon_in[1:],
            velocity_in[:-1],
            heading_in[:-1],
            time_in[1:] - time_in[:-1],
        )
    return residual


def injected_displacement_m(
    orig_lat,
    orig_lon,
    mod_lat,
    mod_lon,
) -> np.ndarray:
    """Return the per-row horizontal displacement in metres.

    Uses the same metre convention as :func:`kinematics.pair_residual_m` and
    the manipulation primitives: north is ``dlat * 111_320``; east is the
    wrapped ``dlon`` times ``111_320 * cos(mid_latitude)``.
    """
    orig_lat_in = _one_dimensional(orig_lat, "orig_lat")
    orig_lon_in = _one_dimensional(orig_lon, "orig_lon")
    mod_lat_in = _one_dimensional(mod_lat, "mod_lat")
    mod_lon_in = _one_dimensional(mod_lon, "mod_lon")
    for name, array in (
        ("orig_lon", orig_lon_in),
        ("mod_lat", mod_lat_in),
        ("mod_lon", mod_lon_in),
    ):
        if array.shape != orig_lat_in.shape:
            raise ValueError(
                f"{name} must have the same shape as orig_lat"
            )

    dlon = (mod_lon_in - orig_lon_in + 180.0) % 360.0 - 180.0
    north = (mod_lat_in - orig_lat_in) * METRES_PER_DEGREE
    east = (
        dlon
        * METRES_PER_DEGREE
        * np.cos(np.deg2rad((orig_lat_in + mod_lat_in) / 2.0))
    )
    return np.hypot(north, east)
