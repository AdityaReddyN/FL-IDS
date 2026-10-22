import numpy as np
import pandas as pd
import pytest

from flids.attacks.kinematics import METRES_PER_DEGREE, pair_residual_m
from flids.attacks.manipulation import (
    altitude_constant,
    constant_horizontal,
    eq12_noise,
    gaussian_horizontal,
    manipulation_streams,
)
from flids.attacks.ramps import ramp_multipliers


def measured_north_east(lat, lon, new_lat, new_lon):
    """Recover north/east displacement with the kinematics metre convention."""
    north = (np.asarray(new_lat) - np.asarray(lat)) * METRES_PER_DEGREE
    dlon = (np.asarray(new_lon) - np.asarray(lon) + 180.0) % 360.0 - 180.0
    mid = np.deg2rad((np.asarray(lat) + np.asarray(new_lat)) / 2.0)
    east = dlon * METRES_PER_DEGREE * np.cos(mid)
    return north, east


def measured_residual(lat, lon, new_lat, new_lon):
    return pair_residual_m(lat, lon, new_lat, new_lon, 0.0, 0.0, 1.0)


def assert_same(first, second):
    assert np.array_equal(
        np.asarray(first), np.asarray(second), equal_nan=True
    )


@pytest.mark.parametrize("latitude", [0.0, 40.0, 60.0])
@pytest.mark.parametrize("bearing", [0.0, 45.0, 90.0, 225.0])
def test_constant_displacement_round_trips_through_kinematics(
    latitude: float, bearing: float
) -> None:
    n_rows = 9
    lat = np.full(n_rows, latitude)
    lon = np.full(n_rows, 10.0)
    multipliers, _ = ramp_multipliers(n_rows, ramp_rows=3, mode="linear_mix")
    magnitude = 5000.0

    result = constant_horizontal(
        lat, lon, multipliers, magnitude, bearing
    )
    assert not result.rejected
    residual = measured_residual(
        lat, lon, result.values["lat"], result.values["lon"]
    )

    assert residual[0] == pytest.approx(0.25 * magnitude, abs=0.1)
    assert residual[1] == pytest.approx(0.50 * magnitude, abs=0.1)
    assert residual[2] == pytest.approx(0.75 * magnitude, abs=0.1)
    assert residual[4] == pytest.approx(magnitude, abs=0.1)
    assert residual[-1] == pytest.approx(0.25 * magnitude, abs=0.1)


def test_constant_bearing_north_and_east() -> None:
    lat = np.array([40.0])
    lon = np.array([10.0])
    a = np.array([1.0])

    north = constant_horizontal(lat, lon, a, 5000.0, 0.0)
    north_m, east_m = measured_north_east(
        lat, lon, north.values["lat"], north.values["lon"]
    )
    assert north_m[0] == pytest.approx(5000.0, abs=0.1)
    assert east_m[0] == pytest.approx(0.0, abs=0.1)

    east = constant_horizontal(lat, lon, a, 5000.0, 90.0)
    north_m, east_m = measured_north_east(
        lat, lon, east.values["lat"], east.values["lon"]
    )
    assert north_m[0] == pytest.approx(0.0, abs=0.1)
    assert east_m[0] == pytest.approx(5000.0, abs=0.1)


def test_constant_longitude_wraps_into_range() -> None:
    result = constant_horizontal(
        np.array([0.0]), np.array([179.99]), np.array([1.0]), 5000.0, 90.0
    )
    assert not result.rejected
    wrapped = result.values["lon"][0]
    assert -180.0 <= wrapped < 180.0
    assert wrapped == pytest.approx(-179.965, abs=0.01)

    west = constant_horizontal(
        np.array([0.0]), np.array([-179.99]), np.array([1.0]), 5000.0, 270.0
    )
    assert -180.0 <= west.values["lon"][0] < 180.0
    assert west.values["lon"][0] > 0.0


def test_constant_latitude_overflow_is_rejected_not_clipped() -> None:
    lat = np.array([89.99])
    lon = np.array([10.0])
    a = np.array([1.0])

    result = constant_horizontal(lat, lon, a, 5000.0, 0.0)
    assert result.rejected
    assert result.reason == "latitude_out_of_range"
    assert_same(result.values["lat"], lat)
    assert_same(result.values["lon"], lon)
    assert_same(result.multipliers, a)


@pytest.mark.parametrize("bearing", [-1.0, 360.0, np.nan, np.inf])
def test_invalid_bearing_raises(bearing: float) -> None:
    with pytest.raises(ValueError, match="bearing"):
        constant_horizontal(
            np.array([0.0]), np.array([0.0]), np.array([1.0]), 500.0, bearing
        )


def test_functions_do_not_mutate_inputs() -> None:
    lat = np.array([40.0, 41.0, 42.0])
    lon = np.array([10.0, 11.0, 12.0])
    a = np.array([1.0, 0.5, 1.0])
    baro = np.array([3000.0, 3100.0, 3200.0])
    geo = np.array([3010.0, 3110.0, 3210.0])
    north = np.array([1.0, 2.0, 3.0])
    east = np.array([4.0, 5.0, 6.0])
    snapshots = {
        "lat": lat.copy(),
        "lon": lon.copy(),
        "a": a.copy(),
        "baro": baro.copy(),
        "geo": geo.copy(),
        "north": north.copy(),
        "east": east.copy(),
    }

    constant_horizontal(lat, lon, a, 500.0, 45.0)
    gaussian_horizontal(lat, lon, a, 250.0, np.random.default_rng(1))
    eq12_noise(north, east, a, 0.2, 25.0, np.random.default_rng(2))
    altitude_constant(baro, geo, a, 35.0, "baro_only")
    altitude_constant(baro, geo, a, 35.0, "baro_plus_geo")

    assert_same(lat, snapshots["lat"])
    assert_same(lon, snapshots["lon"])
    assert_same(a, snapshots["a"])
    assert_same(baro, snapshots["baro"])
    assert_same(geo, snapshots["geo"])
    assert_same(north, snapshots["north"])
    assert_same(east, snapshots["east"])


def test_nan_or_inf_on_active_rows_raises() -> None:
    lat = np.array([40.0, np.nan])
    lon = np.array([10.0, 10.0])
    a = np.array([1.0, 1.0])

    with pytest.raises(ValueError, match="NaN|inf"):
        constant_horizontal(lat, lon, a, 500.0, 0.0)
    with pytest.raises(ValueError, match="NaN|inf"):
        gaussian_horizontal(
            lat, lon, a, 250.0, np.random.default_rng(1)
        )

    with pytest.raises(ValueError, match="NaN|inf"):
        eq12_noise(
            np.array([0.0, np.inf]),
            np.array([0.0, 0.0]),
            a,
            0.2,
            25.0,
            np.random.default_rng(2),
        )

    with pytest.raises(ValueError, match="NaN|inf"):
        altitude_constant(
            np.array([3000.0, np.nan]),
            np.array([3000.0, 3000.0]),
            a,
            35.0,
            "baro_only",
        )
    with pytest.raises(ValueError, match="NaN|inf"):
        altitude_constant(
            np.array([3000.0, 3000.0]),
            np.array([3000.0, np.nan]),
            a,
            35.0,
            "baro_plus_geo",
        )


def test_nan_on_inactive_rows_is_allowed_and_untouched() -> None:
    lat = np.array([np.nan])
    lon = np.array([10.0])
    a = np.array([0.0])

    result = constant_horizontal(lat, lon, a, 500.0, 0.0)
    assert not result.rejected
    assert np.isnan(result.values["lat"][0])
    assert result.values["lon"][0] == 10.0
    assert_same(result.multipliers, a)


def test_gaussian_sample_std_and_mean() -> None:
    n_rows = 25_000
    sigma = 250.0
    lat = np.full(n_rows, 40.0)
    lon = np.full(n_rows, 10.0)
    a = np.ones(n_rows)

    result = gaussian_horizontal(
        lat, lon, a, sigma, np.random.default_rng(2024)
    )
    assert not result.rejected
    north, east = measured_north_east(
        lat, lon, result.values["lat"], result.values["lon"]
    )

    standard_error = sigma / np.sqrt(n_rows)
    for component in (north, east):
        assert np.std(component, ddof=1) == pytest.approx(sigma, rel=0.05)
        assert abs(np.mean(component)) <= 3.0 * standard_error


def test_gaussian_only_changes_active_rows() -> None:
    lat = np.array([40.0, 41.0])
    lon = np.array([10.0, 11.0])
    a = np.array([0.0, 1.0])

    result = gaussian_horizontal(
        lat, lon, a, 250.0, np.random.default_rng(3)
    )
    assert result.values["lat"][0] == lat[0]
    assert result.values["lon"][0] == lon[0]
    assert result.values["lat"][1] != lat[1]


def test_gaussian_is_deterministic_for_the_same_episode_rng() -> None:
    lat = np.full(32, 40.0)
    lon = np.full(32, 10.0)
    a = np.ones(32)

    first = gaussian_horizontal(
        lat, lon, a, 250.0, np.random.default_rng(77)
    )
    second = gaussian_horizontal(
        lat, lon, a, 250.0, np.random.default_rng(77)
    )
    assert_same(first.values["lat"], second.values["lat"])
    assert_same(first.values["lon"], second.values["lon"])


def test_eq12_effective_std_and_active_rows_only() -> None:
    n_rows = 25_000
    kappa = 0.20
    per_step_sigma = 25.0
    a = np.ones(n_rows)
    zeros = np.zeros(n_rows)

    result = eq12_noise(
        zeros,
        zeros,
        a,
        kappa,
        per_step_sigma,
        np.random.default_rng(2025),
    )
    effective_sigma = kappa * per_step_sigma
    for component in (result.values["north"], result.values["east"]):
        assert np.std(component, ddof=1) == pytest.approx(
            effective_sigma, rel=0.05
        )

    north = np.array([1.0, 2.0, 3.0, 4.0])
    east = np.array([5.0, 6.0, 7.0, 8.0])
    sparse = np.array([0.0, 1.0, 0.0, 1.0])
    sparse_result = eq12_noise(
        north, east, sparse, kappa, per_step_sigma, np.random.default_rng(4)
    )
    assert_same(sparse_result.values["north"][[0, 2]], north[[0, 2]])
    assert_same(sparse_result.values["east"][[0, 2]], east[[0, 2]])
    assert sparse_result.values["north"][1] != north[1]
    assert sparse_result.values["east"][3] != east[3]


def test_eq12_kappa_zero_adds_nothing() -> None:
    north = np.array([1.0, 2.0])
    east = np.array([3.0, 4.0])
    a = np.array([1.0, 1.0])
    result = eq12_noise(
        north, east, a, 0.0, 25.0, np.random.default_rng(5)
    )
    assert_same(result.values["north"], north)
    assert_same(result.values["east"], east)


def test_eq12_uses_a_separate_stream_from_gaussian_deviation() -> None:
    lat = np.full(64, 40.0)
    lon = np.full(64, 10.0)
    a = np.ones(64)
    zeros = np.zeros(64)

    def gaussian_draw(include_noise: bool) -> tuple[np.ndarray, np.ndarray]:
        episode_rng = np.random.default_rng(99)
        gaussian_rng, noise_rng = manipulation_streams(episode_rng)
        if include_noise:
            eq12_noise(
                zeros, zeros, a, 0.2, 25.0, noise_rng
            )
        result = gaussian_horizontal(
            lat, lon, a, 250.0, gaussian_rng
        )
        return result.values["lat"], result.values["lon"]

    without_noise = gaussian_draw(False)
    with_noise = gaussian_draw(True)
    assert_same(without_noise[0], with_noise[0])
    assert_same(without_noise[1], with_noise[1])

    different_episode = np.random.default_rng(100)
    other_gaussian, _ = manipulation_streams(different_episode)
    other = gaussian_horizontal(lat, lon, a, 250.0, other_gaussian)
    assert not np.array_equal(other.values["lat"], without_noise[0])


def test_manipulation_streams_are_independent_children() -> None:
    first_episode = np.random.default_rng(7)
    first_gaussian, first_noise = manipulation_streams(first_episode)
    second_episode = np.random.default_rng(7)
    second_gaussian, second_noise = manipulation_streams(second_episode)

    assert_same(first_gaussian.random(8), second_gaussian.random(8))
    assert_same(first_noise.random(8), second_noise.random(8))
    assert not np.array_equal(
        np.random.default_rng(7).spawn(2)[0].random(8),
        np.random.default_rng(7).spawn(2)[1].random(8),
    )


def test_altitude_variants() -> None:
    baro = np.array([3000.0, 3000.0])
    geo = np.array([3010.0, 3010.0])
    a = np.array([1.0, 0.5])
    shift = 35.0

    baro_only = altitude_constant(baro, geo, a, shift, "baro_only")
    assert baro_only.values["baroaltitude"].tolist() == [3035.0, 3017.5]
    assert_same(baro_only.values["geoaltitude"], geo)

    both = altitude_constant(baro, geo, a, shift, "baro_plus_geo")
    assert both.values["baroaltitude"].tolist() == [3035.0, 3017.5]
    assert both.values["geoaltitude"].tolist() == [3045.0, 3027.5]


def test_baro_only_altitude_constant_does_not_require_geo() -> None:
    result = altitude_constant(
        np.array([3000.0, 3000.0]), None, np.array([1.0, 0.5]), 35.0,
        "baro_only",
    )
    assert result.values["baroaltitude"].tolist() == [3035.0, 3017.5]
    assert "geoaltitude" not in result.values


@pytest.mark.parametrize(
    "baro,geo,shift",
    [
        (100.0, 3000.0, -1000.0),
        (19_990.0, 3000.0, 100.0),
        (3000.0, 19_990.0, 100.0),
    ],
)
def test_altitude_bounds_are_rejected(
    baro: float, geo: float, shift: float
) -> None:
    baro_arr = np.array([baro])
    geo_arr = np.array([geo])
    a = np.array([1.0])
    result = altitude_constant(
        baro_arr, geo_arr, a, shift, "baro_plus_geo"
    )
    assert result.rejected
    assert result.reason == "altitude_out_of_range"
    assert_same(result.values["baroaltitude"], baro_arr)
    assert_same(result.values["geoaltitude"], geo_arr)


def test_altitude_bounds_are_inclusive() -> None:
    result = altitude_constant(
        np.array([-450.0]),
        np.array([19_950.0]),
        np.array([1.0]),
        -50.0,
        "baro_plus_geo",
    )
    assert not result.rejected
    assert result.values["baroaltitude"][0] == -500.0

    result = altitude_constant(
        np.array([19_950.0]),
        np.array([19_950.0]),
        np.array([1.0]),
        50.0,
        "baro_plus_geo",
    )
    assert not result.rejected
    assert result.values["geoaltitude"][0] == 20_000.0


def test_altitude_rejects_unknown_variant() -> None:
    with pytest.raises(ValueError, match="variant"):
        altitude_constant(
            np.array([3000.0]),
            np.array([3000.0]),
            np.array([1.0]),
            35.0,
            "geo_only",
        )


def test_metadata_and_flags_are_not_touched() -> None:
    frame = pd.DataFrame(
        {
            "lat": [40.0, 41.0],
            "lon": [10.0, 11.0],
            "baroaltitude": [3000.0, 3100.0],
            "geoaltitude": [3010.0, 3110.0],
            "onground": [False, True],
            "contact_lag_seconds": [1.0, np.nan],
            "contact_lag_missing": [False, True],
            "lat_missing": [False, True],
            "lon_missing": [False, True],
        }
    )
    snapshot = frame.copy(deep=True)
    a = np.array([1.0, 1.0])

    results = [
        constant_horizontal(
            frame["lat"].to_numpy(),
            frame["lon"].to_numpy(),
            a,
            500.0,
            45.0,
        ),
        gaussian_horizontal(
            frame["lat"].to_numpy(),
            frame["lon"].to_numpy(),
            a,
            250.0,
            np.random.default_rng(6),
        ),
        altitude_constant(
            frame["baroaltitude"].to_numpy(),
            frame["geoaltitude"].to_numpy(),
            a,
            35.0,
            "baro_plus_geo",
        ),
    ]

    pd.testing.assert_frame_equal(frame, snapshot)
    allowed = {"lat", "lon", "baroaltitude", "geoaltitude"}
    for result in results:
        assert set(result.values) <= allowed
