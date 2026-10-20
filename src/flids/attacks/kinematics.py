"""Kinematic helpers shared by eligibility and placement.

Metre convention (identical to ``scripts/calibrate_v3_stage1.py`` lines
415--419): local north is ``dlat * 111_320``; local east is
``dlon * 111_320 * cos(mid_latitude)``. Heading is degrees clockwise from north,
so the expected displacement is ``velocity * dt * (cos h, sin h)``.
"""

from __future__ import annotations

import numpy as np

METRES_PER_DEGREE = 111_320.0
SPEED_BAND_NAMES: tuple[str, str, str, str] = (
    "0_50",
    "50_100",
    "100_200",
    "200_plus",
)


def speed_band(velocity_mps):
    """Return the lower-inclusive, upper-exclusive speed band.

    ``NaN`` maps to ``"missing"`` and negative speeds to ``"invalid"``. The
    function is vectorized; a scalar input returns a Python string, an array
    input returns a string ndarray.
    """
    values = np.asarray(velocity_mps, dtype=float)
    scalar = values.ndim == 0
    array = np.atleast_1d(values)
    output = np.empty(array.shape, dtype="<U8")

    missing = np.isnan(array)
    output[missing] = "missing"
    invalid = ~missing & (array < 0.0)
    output[invalid] = "invalid"

    valid = ~missing & (array >= 0.0)
    output[valid & (array < 50.0)] = "0_50"
    output[valid & (array >= 50.0) & (array < 100.0)] = "50_100"
    output[valid & (array >= 100.0) & (array < 200.0)] = "100_200"
    output[valid & (array >= 200.0)] = "200_plus"

    return output.item() if scalar else output


def pair_residual_m(
    lat_i,
    lon_i,
    lat_j,
    lon_j,
    velocity_i,
    heading_i_deg,
    dt_s,
):
    """Horizontal residual between observed and heading-implied displacement.

    The longitude difference is wrapped into ``[-180, 180]`` before conversion
    so antimeridian-crossing pairs are handled correctly. Returns a float for
    scalar inputs and an ndarray for array inputs.
    """
    lat_i = np.asarray(lat_i, dtype=float)
    lon_i = np.asarray(lon_i, dtype=float)
    lat_j = np.asarray(lat_j, dtype=float)
    lon_j = np.asarray(lon_j, dtype=float)
    velocity_i = np.asarray(velocity_i, dtype=float)
    heading_i_deg = np.asarray(heading_i_deg, dtype=float)
    dt_s = np.asarray(dt_s, dtype=float)

    dlon = (lon_j - lon_i + 180.0) % 360.0 - 180.0
    north = (lat_j - lat_i) * METRES_PER_DEGREE
    east = (
        dlon
        * METRES_PER_DEGREE
        * np.cos(np.deg2rad((lat_i + lat_j) / 2.0))
    )

    expected = velocity_i * dt_s
    expected_north = expected * np.cos(np.deg2rad(heading_i_deg))
    expected_east = expected * np.sin(np.deg2rad(heading_i_deg))
    residual = np.hypot(north - expected_north, east - expected_east)

    return float(residual) if np.ndim(residual) == 0 else residual
