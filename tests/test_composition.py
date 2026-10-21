"""Composition tests for manipulation primitives (D-023).

The hard-coded arrays below were produced from the pre-refactor
``constant_horizontal`` / ``gaussian_horizontal`` implementation at commit
3b64bb0 and stored as float hex literals, so equality is bit-for-bit.
"""

import numpy as np
import pytest

from flids.attacks.detectability import injected_displacement_m
from flids.attacks.manipulation import (
    add_scaled_eq12_noise,
    apply_horizontal_displacement,
    constant_horizontal,
    gaussian_horizontal,
    gradual_horizontal,
    horizontal_displacement_constant,
    horizontal_displacement_gaussian,
)
from flids.attacks.ramps import effective_row_count, ramp_multipliers

LAT = np.array([40.0, 40.5, 41.0, 10.0, -5.0])
LON = np.array([10.0, 11.0, 179.999, -179.999, 0.0])
A = np.array([0.25, 0.5, 1.0, 0.0, 1.0])

CONSTANT_LAT = [
    "0x1.401411ab1e36cp+5",
    "0x1.442823563c6d7p+5",
    "0x1.485046ac78daep+5",
    "0x1.4000000000000p+3",
    "-0x1.3d7dca9c3928fp+2",
]
CONSTANT_LON = [
    "0x1.40506a8ecdea0p+3",
    "0x1.60a209805f4f0p+3",
    "-0x1.67ec19f4f4f9cp+7",
    "-0x1.67ff7ced91687p+7",
    "0x1.eea6cb0996000p-6",
]
GAUSSIAN_LAT = [
    "0x1.3ffe06c460b83p+5",
    "0x1.43fe4d1afec8dp+5",
    "0x1.4800ef27cfaebp+5",
    "0x1.4000000000000p+3",
    "-0x1.401d5ce224680p+2",
]
GAUSSIAN_LON = [
    "0x1.3ffe6a996eee0p+3",
    "0x1.5fffdbbc86d20p+3",
    "0x1.67fe62d4bc614p+7",
    "-0x1.67ff7ced91687p+7",
    "0x1.86e57923e0000p-9",
]


def from_hex(values):
    return np.array([float.fromhex(value) for value in values])


def assert_same(first, second) -> None:
    assert np.array_equal(
        np.asarray(first), np.asarray(second), equal_nan=True
    )


def test_constant_wrapper_is_bit_identical_to_pre_refactor_output() -> None:
    result = constant_horizontal(LAT, LON, A, 5500.0, 37.5)
    assert not result.rejected
    assert_same(result.values["lat"], from_hex(CONSTANT_LAT))
    assert_same(result.values["lon"], from_hex(CONSTANT_LON))
    assert_same(result.multipliers, A)


def test_gaussian_wrapper_is_bit_identical_to_pre_refactor_output() -> None:
    result = gaussian_horizontal(
        LAT, LON, A, 250.0, np.random.default_rng(20261021)
    )
    assert not result.rejected
    assert_same(result.values["lat"], from_hex(GAUSSIAN_LAT))
    assert_same(result.values["lon"], from_hex(GAUSSIAN_LON))
    assert_same(result.multipliers, A)


def test_constant_composition_equals_wrapper() -> None:
    north_m, east_m = horizontal_displacement_constant(A, 5500.0, 37.5)
    composed = apply_horizontal_displacement(LAT, LON, A, north_m, east_m)
    wrapper = constant_horizontal(LAT, LON, A, 5500.0, 37.5)

    assert_same(composed.values["lat"], wrapper.values["lat"])
    assert_same(composed.values["lon"], wrapper.values["lon"])
    assert_same(composed.values["lat"], from_hex(CONSTANT_LAT))


def test_gaussian_composition_equals_wrapper() -> None:
    north_m, east_m = horizontal_displacement_gaussian(
        A, 250.0, np.random.default_rng(20261021)
    )
    composed = apply_horizontal_displacement(LAT, LON, A, north_m, east_m)
    wrapper = gaussian_horizontal(
        LAT, LON, A, 250.0, np.random.default_rng(20261021)
    )

    assert_same(composed.values["lat"], wrapper.values["lat"])
    assert_same(composed.values["lon"], wrapper.values["lon"])
    assert_same(composed.values["lat"], from_hex(GAUSSIAN_LAT))


def test_apply_does_not_rescale_components_by_a() -> None:
    lat = np.array([40.0])
    lon = np.array([10.0])
    result = apply_horizontal_displacement(
        lat, lon, np.array([0.5]), np.array([1000.0]), np.array([0.0])
    )
    assert not result.rejected
    assert_same(result.multipliers, np.array([0.5]))
    measured = injected_displacement_m(
        lat, lon, result.values["lat"], result.values["lon"]
    )
    assert measured[0] == pytest.approx(1000.0, abs=0.1)


def test_constant_composition_round_trips_through_injected_displacement() -> None:
    n_rows = 60
    lat = np.full(n_rows, 40.0)
    lon = np.full(n_rows, 10.0)
    a, _ = ramp_multipliers(n_rows, ramp_rows=3, mode="linear_mix")

    north_m, east_m = horizontal_displacement_constant(a, 6000.0, 123.0)
    result = apply_horizontal_displacement(lat, lon, a, north_m, east_m)
    measured = injected_displacement_m(
        lat, lon, result.values["lat"], result.values["lon"]
    )
    assert np.allclose(measured, 6000.0 * a, atol=0.1)


def test_gradual_realized_multipliers_and_measured_displacement() -> None:
    n_rows = 60
    magnitude = 6000.0
    bearing = 123.0
    lat = np.full(n_rows, 40.0)
    lon = np.full(n_rows, 10.0)
    a, _ = ramp_multipliers(n_rows, ramp_rows=3, mode="linear_mix")
    g = np.arange(n_rows, dtype=float) / (n_rows - 1)

    result = gradual_horizontal(lat, lon, a, magnitude, bearing)
    assert not result.rejected
    assert_same(result.multipliers, a * g)

    measured = injected_displacement_m(
        lat, lon, result.values["lat"], result.values["lon"]
    )
    assert np.allclose(measured, magnitude * g * a, atol=0.1)
    assert measured[0] == 0.0
    assert measured[-1] == pytest.approx(0.25 * magnitude, abs=0.1)


def test_gradual_single_row_uses_fraction_one() -> None:
    lat = np.array([40.0])
    lon = np.array([10.0])
    a = np.array([1.0])

    result = gradual_horizontal(lat, lon, a, 1000.0, 90.0)
    assert_same(result.multipliers, np.array([1.0]))
    measured = injected_displacement_m(
        lat, lon, result.values["lat"], result.values["lon"]
    )
    assert measured[0] == pytest.approx(1000.0, abs=0.1)


def test_gradual_effective_row_counts() -> None:
    def realized(n_rows: int) -> np.ndarray:
        a, _ = ramp_multipliers(n_rows, ramp_rows=3, mode="linear_mix")
        result = gradual_horizontal(
            np.full(n_rows, 40.0),
            np.full(n_rows, 10.0),
            a,
            6000.0,
            123.0,
        )
        return result.multipliers

    assert effective_row_count(realized(12)) == 4
    assert effective_row_count(realized(60)) == 28


def test_gradual_a_zero_rows_are_bit_identical() -> None:
    lat = np.array([40.0, 41.0, 42.0])
    lon = np.array([10.0, 11.0, np.nan])
    a = np.array([0.0, 1.0, 0.0])

    result = gradual_horizontal(lat, lon, a, 6000.0, 45.0)
    assert result.values["lat"][0] == lat[0]
    assert result.values["lon"][0] == lon[0]
    assert result.values["lat"][2] == lat[2]
    assert np.isnan(result.values["lon"][2])
    assert result.values["lat"][1] != lat[1]


def test_scaled_eq12_noise_effective_std_and_scaling() -> None:
    n_rows = 25_000
    kappa = 0.20
    per_step_sigma = 25.0
    zeros = np.zeros(n_rows)

    full = add_scaled_eq12_noise(
        zeros,
        zeros,
        np.ones(n_rows),
        kappa,
        per_step_sigma,
        np.random.default_rng(2026),
    )
    for component in full:
        assert np.std(component, ddof=1) == pytest.approx(
            kappa * per_step_sigma, rel=0.05
        )

    half = add_scaled_eq12_noise(
        zeros,
        zeros,
        np.full(n_rows, 0.5),
        kappa,
        per_step_sigma,
        np.random.default_rng(2027),
    )
    for component in half:
        assert np.std(component, ddof=1) == pytest.approx(
            0.5 * kappa * per_step_sigma, rel=0.05
        )


def test_scaled_eq12_noise_zero_multiplier_and_kappa_zero() -> None:
    north = np.array([1.0, 2.0, 3.0])
    east = np.array([4.0, 5.0, 6.0])
    sparse = np.array([0.0, 1.0, 0.0])

    result_north, result_east = add_scaled_eq12_noise(
        north, east, sparse, 0.2, 25.0, np.random.default_rng(4)
    )
    assert_same(result_north[[0, 2]], north[[0, 2]])
    assert_same(result_east[[0, 2]], east[[0, 2]])
    assert result_north[1] != north[1]

    zero_kappa = add_scaled_eq12_noise(
        north, east, np.ones(3), 0.0, 25.0, np.random.default_rng(5)
    )
    assert_same(zero_kappa[0], north)
    assert_same(zero_kappa[1], east)


def test_new_functions_do_not_mutate_inputs() -> None:
    lat = LAT.copy()
    lon = LON.copy()
    a = A.copy()
    north = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    east = np.array([6.0, 7.0, 8.0, 9.0, 10.0])
    snapshots = [lat.copy(), lon.copy(), a.copy(), north.copy(), east.copy()]

    horizontal_displacement_constant(a, 5500.0, 37.5)
    horizontal_displacement_gaussian(
        a, 250.0, np.random.default_rng(1)
    )
    apply_horizontal_displacement(lat, lon, a, north, east)
    add_scaled_eq12_noise(
        north, east, a, 0.2, 25.0, np.random.default_rng(2)
    )
    gradual_horizontal(lat, lon, a, 5500.0, 37.5)

    for current, snapshot in zip(
        [lat, lon, a, north, east], snapshots
    ):
        assert_same(current, snapshot)


def test_new_functions_are_deterministic() -> None:
    lat = np.full(60, 40.0)
    lon = np.full(60, 10.0)
    a, _ = ramp_multipliers(60, ramp_rows=3, mode="linear_mix")

    first = gradual_horizontal(lat, lon, a, 6000.0, 123.0)
    second = gradual_horizontal(lat, lon, a, 6000.0, 123.0)
    assert_same(first.values["lat"], second.values["lat"])
    assert_same(first.values["lon"], second.values["lon"])

    first_noise = add_scaled_eq12_noise(
        np.zeros(60), np.zeros(60), a, 0.2, 25.0,
        np.random.default_rng(11),
    )
    second_noise = add_scaled_eq12_noise(
        np.zeros(60), np.zeros(60), a, 0.2, 25.0,
        np.random.default_rng(11),
    )
    assert_same(first_noise[0], second_noise[0])
    assert_same(first_noise[1], second_noise[1])
