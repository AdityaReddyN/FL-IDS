"""Detectability reporting helpers (D-023)."""

import numpy as np
import pytest

from flids.attacks.detectability import (
    injected_displacement_m,
    residual_series,
)
from flids.attacks.kinematics import pair_residual_m


def test_residual_series_matches_pair_residual_m() -> None:
    lat = np.array([40.0, 40.001, 40.003, 40.003])
    lon = np.array([10.0, 10.002, 10.002, 9.998])
    velocity = np.array([100.0, 120.0, 80.0, 150.0])
    heading = np.array([0.0, 45.0, 90.0, 180.0])
    time = np.array([0, 10, 20, 30], dtype=np.int64)

    residual = residual_series(lat, lon, velocity, heading, time)
    assert np.isnan(residual[0])
    for k in range(1, len(lat)):
        expected = pair_residual_m(
            lat[k - 1],
            lon[k - 1],
            lat[k],
            lon[k],
            velocity[k - 1],
            heading[k - 1],
            time[k] - time[k - 1],
        )
        assert residual[k] == pytest.approx(expected, abs=1e-9)


def test_residual_series_uses_the_earlier_row_velocity_and_heading() -> None:
    # 1000 m east over 10 s is expected exactly at 100 m/s heading 90.
    lat = np.array([40.0, 40.0])
    lon = np.array([10.0, 10.0 + 1000.0 / (111_320.0 * np.cos(np.deg2rad(40.0)))])
    time = np.array([0, 10], dtype=np.int64)

    matching = residual_series(
        lat, lon, np.array([100.0, 999.0]), np.array([90.0, 0.0]), time
    )
    assert matching[1] == pytest.approx(0.0, abs=0.1)

    mismatching = residual_series(
        lat, lon, np.array([0.0, 100.0]), np.array([0.0, 90.0]), time
    )
    assert mismatching[1] == pytest.approx(1000.0, abs=1.0)


def test_residual_series_handles_short_and_antimeridian_inputs() -> None:
    assert residual_series(
        np.array([]), np.array([]), np.array([]), np.array([]), np.array([])
    ).shape == (0,)

    single = residual_series(
        np.array([40.0]),
        np.array([10.0]),
        np.array([100.0]),
        np.array([0.0]),
        np.array([0]),
    )
    assert single.shape == (1,)
    assert np.isnan(single[0])

    crossing = residual_series(
        np.array([0.0, 0.0]),
        np.array([179.99, -179.99]),
        np.array([222.64, 222.64]),
        np.array([90.0, 90.0]),
        np.array([0, 10]),
    )
    assert crossing[1] == pytest.approx(0.0, abs=0.5)


def test_injected_displacement_uses_the_shared_metre_convention() -> None:
    orig_lat = np.array([40.0, 40.0])
    orig_lon = np.array([10.0, 10.0])
    mod_lat = np.array([40.0 + 1000.0 / 111_320.0, 40.0])
    mod_lon = np.array([10.0, 10.0 + 500.0 / (
        111_320.0 * np.cos(np.deg2rad(40.0))
    )])

    displacement = injected_displacement_m(
        orig_lat, orig_lon, mod_lat, mod_lon
    )
    assert displacement[0] == pytest.approx(1000.0, abs=0.1)
    assert displacement[1] == pytest.approx(500.0, abs=0.1)


def test_injected_displacement_handles_antimeridian_and_identity() -> None:
    crossing = injected_displacement_m(
        np.array([0.0]), np.array([179.99]),
        np.array([0.0]), np.array([-179.99]),
    )
    assert crossing[0] == pytest.approx(
        0.02 * 111_320.0, abs=0.5
    )

    identity = injected_displacement_m(
        np.array([40.0]), np.array([10.0]),
        np.array([40.0]), np.array([10.0]),
    )
    assert identity[0] == 0.0


def test_detectability_helpers_do_not_mutate_inputs() -> None:
    arrays = [
        np.array([40.0, 40.1]),
        np.array([10.0, 10.1]),
        np.array([100.0, 110.0]),
        np.array([0.0, 10.0]),
        np.array([0, 10], dtype=np.int64),
    ]
    snapshots = [array.copy() for array in arrays]
    residual_series(*arrays)
    injected_displacement_m(arrays[0], arrays[1], arrays[0], arrays[1])
    for array, snapshot in zip(arrays, snapshots):
        assert np.array_equal(array, snapshot)
