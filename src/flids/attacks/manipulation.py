"""Row-level manipulation primitives for one segment (D-022).

Every function is pure: it copies its inputs, changes only rows with
``a_t > 0``, and returns a :class:`ManipulationResult`. Rows with ``a_t == 0``
are copied through bit-identically. Metadata such as ``onground``,
``contact_lag_*`` and the ``*_missing`` flags is never accepted or touched by
these functions.

Horizontal displacement uses the same local-metre convention as
``kinematics.pair_residual_m`` (D-022)::

    new_lat = lat + north_m / 111_320
    new_lon = lon + east_m / (111_320 * cos(radians((lat + new_lat) / 2)))

Longitude is wrapped into ``[-180, 180)``. Bearings are supplied by the caller
in degrees in ``[0, 360)``; values outside that range raise ``ValueError``
(they are not wrapped). A resulting latitude outside ``[-90, 90]`` rejects the
whole call with ``reason="latitude_out_of_range"``; nothing is clipped.

Provisional values (D-022, copied from the proposed YAML for convenience; the
functions never read the YAML and always take explicit arguments)
--------------------------------------------------------------------------
* horizontal tier magnitudes: 500 / 2_500 / 5_500 / 11_000 m
* Gaussian tier sigmas: 250 / 1_250 / 2_750 / 5_500 m
* Eq. 12 kappa: 0.20 / 0.10 / 0.05 / 0.0
* Eq. 12 per-step sigma: 25.0 m
* altitude shifts: 35 / 125 / 250 / 500 m

These values are provisional and not approved design.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .kinematics import METRES_PER_DEGREE

ACTIVE_THRESHOLD = 0.0
ALTITUDE_MIN_METERS = -500.0
ALTITUDE_MAX_METERS = 20_000.0
LATITUDE_MIN_DEGREES = -90.0
LATITUDE_MAX_DEGREES = 90.0

PROVISIONAL_HORIZONTAL_METERS = {
    "subtle": 500.0,
    "moderate": 2_500.0,
    "blatant": 5_500.0,
    "gross_positive_control": 11_000.0,
}
PROVISIONAL_GAUSSIAN_SIGMA_METERS = {
    "subtle": 250.0,
    "moderate": 1_250.0,
    "blatant": 2_750.0,
    "gross_positive_control": 5_500.0,
}
PROVISIONAL_EQ12_KAPPA = {
    "subtle": 0.20,
    "moderate": 0.10,
    "blatant": 0.05,
    "gross_positive_control": 0.0,
}
PROVISIONAL_PER_STEP_NOISE_SIGMA_METERS = 25.0
PROVISIONAL_ALTITUDE_SHIFT_METERS = {
    "subtle": 35.0,
    "moderate": 125.0,
    "blatant": 250.0,
    "gross_positive_control": 500.0,
}


@dataclass(frozen=True)
class ManipulationResult:
    """Modified arrays plus the per-row multiplier and rejection status.

    ``values`` holds only the arrays this operation modifies. ``rejected``
    calls return copies of the unmodified inputs.
    """

    values: dict[str, np.ndarray]
    multipliers: np.ndarray
    rejected: bool = False
    reason: str | None = None


def manipulation_streams(episode_rng) -> tuple:
    """Return independent ``(gaussian_rng, eq12_rng)`` children of an episode RNG.

    Deriving both children once with ``Generator.spawn`` means that calling or
    skipping :func:`eq12_noise` never changes the Gaussian-deviation draws for
    the same episode (D-022).
    """
    gaussian_rng, eq12_rng = episode_rng.spawn(2)
    return gaussian_rng, eq12_rng


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


def _paired_arrays(first, second, first_name: str, second_name: str):
    first_array = _one_dimensional(first, first_name)
    second_array = _one_dimensional(second, second_name)
    if first_array.shape != second_array.shape:
        raise ValueError(
            f"{first_name} and {second_name} must have the same shape"
        )
    return first_array, second_array


def _require_finite_on_active(active, arrays: dict[str, np.ndarray]) -> None:
    for name, array in arrays.items():
        if np.any(active & ~np.isfinite(array)):
            raise ValueError(
                f"{name} contains NaN or inf on rows with a_t > 0"
            )


def _new_latitude(lat: np.ndarray, north_m: np.ndarray) -> np.ndarray:
    return lat + north_m / METRES_PER_DEGREE


def _new_longitude(
    lat: np.ndarray,
    new_lat: np.ndarray,
    lon: np.ndarray,
    east_m: np.ndarray,
) -> np.ndarray:
    scale = METRES_PER_DEGREE * np.cos(
        np.deg2rad((lat + new_lat) / 2.0)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        east_degrees = east_m / scale
    return (lon + east_degrees + 180.0) % 360.0 - 180.0


def _reject(
    values: dict[str, np.ndarray],
    multipliers: np.ndarray,
    reason: str,
) -> ManipulationResult:
    return ManipulationResult(
        values=values,
        multipliers=multipliers,
        rejected=True,
        reason=reason,
    )


def _horizontal_result(
    lat: np.ndarray,
    lon: np.ndarray,
    multipliers: np.ndarray,
    north_m: np.ndarray,
    east_m: np.ndarray,
) -> ManipulationResult:
    active = multipliers > ACTIVE_THRESHOLD
    new_lat = _new_latitude(lat, north_m)

    overflow = active & (
        (new_lat < LATITUDE_MIN_DEGREES)
        | (new_lat > LATITUDE_MAX_DEGREES)
    )
    if np.any(overflow):
        return _reject(
            {"lat": lat, "lon": lon},
            multipliers,
            "latitude_out_of_range",
        )

    new_lon = _new_longitude(lat, new_lat, lon, east_m)
    if np.any(active & ~np.isfinite(new_lon)):
        return _reject(
            {"lat": lat, "lon": lon},
            multipliers,
            "longitude_scale_undefined",
        )

    lat_out = lat.copy()
    lon_out = lon.copy()
    lat_out[active] = new_lat[active]
    lon_out[active] = new_lon[active]
    return ManipulationResult(
        values={"lat": lat_out, "lon": lon_out}, multipliers=multipliers
    )


def constant_horizontal(
    lat,
    lon,
    a,
    magnitude_m: float,
    bearing_deg: float,
) -> ManipulationResult:
    """Apply a constant horizontal displacement of ``magnitude_m``.

    North is ``magnitude_m * cos(bearing)``; east is
    ``magnitude_m * sin(bearing)``; both are multiplied by ``a_t``. The
    bearing must lie in ``[0, 360)``; 360 raises rather than wrapping.
    """
    lat_in, lon_in = _paired_arrays(lat, lon, "lat", "lon")
    multipliers = _multipliers(a, lat_in.size)

    magnitude = float(magnitude_m)
    if not np.isfinite(magnitude) or magnitude < 0.0:
        raise ValueError("magnitude_m must be finite and non-negative")

    bearing = float(bearing_deg)
    if not np.isfinite(bearing) or not 0.0 <= bearing < 360.0:
        raise ValueError("bearing_deg must be finite and in [0, 360)")

    active = multipliers > ACTIVE_THRESHOLD
    _require_finite_on_active(active, {"lat": lat_in, "lon": lon_in})

    radians = np.deg2rad(bearing)
    north_m = magnitude * np.cos(radians) * multipliers
    east_m = magnitude * np.sin(radians) * multipliers
    return _horizontal_result(
        lat_in, lon_in, multipliers, north_m, east_m
    )


def gaussian_horizontal(
    lat,
    lon,
    a,
    sigma_m: float,
    rng,
) -> ManipulationResult:
    """Apply per-row independent ``N(0, sigma_m**2)`` north/east offsets.

    Each component is drawn independently per row and multiplied by ``a_t``.
    Use :func:`manipulation_streams` so Eq. 12 noise cannot perturb these draws.
    """
    lat_in, lon_in = _paired_arrays(lat, lon, "lat", "lon")
    multipliers = _multipliers(a, lat_in.size)

    sigma = float(sigma_m)
    if not np.isfinite(sigma) or sigma < 0.0:
        raise ValueError("sigma_m must be finite and non-negative")

    active = multipliers > ACTIVE_THRESHOLD
    _require_finite_on_active(active, {"lat": lat_in, "lon": lon_in})

    draws = rng.normal(loc=0.0, scale=sigma, size=(lat_in.size, 2))
    north_m = draws[:, 0] * multipliers
    east_m = draws[:, 1] * multipliers
    return _horizontal_result(
        lat_in, lon_in, multipliers, north_m, east_m
    )


def eq12_noise(
    values_m_north,
    values_m_east,
    a,
    kappa: float,
    per_step_sigma_m: float,
    rng,
) -> ManipulationResult:
    """Add ``kappa * N(0, per_step_sigma_m**2)`` per component on ``a_t > 0``.

    The effective added standard deviation is ``kappa * per_step_sigma_m``.
    With ``kappa == 0`` no draws are made and the inputs are returned
    unchanged. Pass the dedicated Eq. 12 child from
    :func:`manipulation_streams`.
    """
    north_in, east_in = _paired_arrays(
        values_m_north, values_m_east, "values_m_north", "values_m_east"
    )
    multipliers = _multipliers(a, north_in.size)

    kappa_value = float(kappa)
    if not np.isfinite(kappa_value) or kappa_value < 0.0:
        raise ValueError("kappa must be finite and non-negative")
    per_step_sigma = float(per_step_sigma_m)
    if not np.isfinite(per_step_sigma) or per_step_sigma < 0.0:
        raise ValueError(
            "per_step_sigma_m must be finite and non-negative"
        )

    active = multipliers > ACTIVE_THRESHOLD
    _require_finite_on_active(
        active, {"values_m_north": north_in, "values_m_east": east_in}
    )

    north_out = north_in.copy()
    east_out = east_in.copy()
    if kappa_value > 0.0 and np.any(active):
        draws = rng.normal(
            loc=0.0,
            scale=per_step_sigma,
            size=(north_in.size, 2),
        )
        north_out[active] = (
            north_in[active] + kappa_value * draws[active, 0]
        )
        east_out[active] = (
            east_in[active] + kappa_value * draws[active, 1]
        )
    return ManipulationResult(
        values={"north": north_out, "east": east_out},
        multipliers=multipliers,
    )


def altitude_constant(
    baro,
    geo,
    a,
    shift_m: float,
    variant: str,
) -> ManipulationResult:
    """Apply a constant altitude shift, scaled by ``a_t``.

    ``variant="baro_only"`` changes ``baroaltitude`` only;
    ``variant="baro_plus_geo"`` applies the same signed shift to both. The
    caller chooses the sign. Any active resulting altitude below -500 m or
    above 20,000 m rejects the whole call.
    """
    if variant not in ("baro_only", "baro_plus_geo"):
        raise ValueError(
            "variant must be 'baro_only' or 'baro_plus_geo'"
        )

    baro_in, geo_in = _paired_arrays(
        baro, geo, "baroaltitude", "geoaltitude"
    )
    multipliers = _multipliers(a, baro_in.size)

    shift = float(shift_m)
    if not np.isfinite(shift):
        raise ValueError("shift_m must be finite")

    active = multipliers > ACTIVE_THRESHOLD
    targets = {"baroaltitude": baro_in}
    if variant == "baro_plus_geo":
        targets["geoaltitude"] = geo_in
    _require_finite_on_active(active, targets)

    delta = multipliers * shift
    baro_out = baro_in.copy()
    geo_out = geo_in.copy()
    baro_out[active] = baro_in[active] + delta[active]
    if variant == "baro_plus_geo":
        geo_out[active] = geo_in[active] + delta[active]

    changed = [baro_out]
    if variant == "baro_plus_geo":
        changed.append(geo_out)
    out_of_bounds = np.zeros(baro_in.size, dtype=bool)
    for values in changed:
        out_of_bounds |= active & (
            (values < ALTITUDE_MIN_METERS)
            | (values > ALTITUDE_MAX_METERS)
        )
    if np.any(out_of_bounds):
        return _reject(
            {"baroaltitude": baro_in, "geoaltitude": geo_in},
            multipliers,
            "altitude_out_of_range",
        )

    return ManipulationResult(
        values={"baroaltitude": baro_out, "geoaltitude": geo_out},
        multipliers=multipliers,
    )
