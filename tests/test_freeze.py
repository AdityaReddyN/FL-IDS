"""Freeze primitives: anchor blending and strict-before anchor lookup (D-023)."""

import numpy as np
import pytest

from flids.attacks.freeze import anchor_from_offsets, freeze_lat_lon


def assert_same(first, second) -> None:
    assert np.array_equal(
        np.asarray(first), np.asarray(second), equal_nan=True
    )


def test_freeze_holds_anchor_and_ramps() -> None:
    lat = np.array([40.0, 41.0, 42.0])
    lon = np.array([10.0, 11.0, 12.0])
    a = np.array([0.0, 0.5, 1.0])

    result = freeze_lat_lon(lat, lon, a, 50.0, 60.0)
    assert not result.rejected
    assert result.values["lat"][0] == 40.0
    assert result.values["lon"][0] == 10.0
    assert result.values["lat"][1] == pytest.approx(45.5)
    assert result.values["lon"][1] == pytest.approx(35.5)
    assert result.values["lat"][2] == 50.0
    assert result.values["lon"][2] == 60.0
    assert_same(result.multipliers, a)


def test_freeze_longitude_blends_across_the_antimeridian() -> None:
    result = freeze_lat_lon(
        np.array([40.0]), np.array([179.9]), np.array([0.5]), 40.0, -179.9
    )
    assert result.values["lon"][0] == pytest.approx(-180.0, abs=1e-9)
    assert -180.0 <= result.values["lon"][0] < 180.0


def test_freeze_a_zero_rows_are_bit_identical() -> None:
    lat = np.array([np.nan, 41.0])
    lon = np.array([10.0, 11.0])
    a = np.array([0.0, 1.0])

    result = freeze_lat_lon(lat, lon, a, 50.0, 60.0)
    assert np.isnan(result.values["lat"][0])
    assert result.values["lon"][0] == 10.0
    assert result.values["lat"][1] == 50.0


def test_freeze_only_returns_lat_lon() -> None:
    result = freeze_lat_lon(
        np.array([40.0]), np.array([10.0]), np.array([1.0]), 41.0, 11.0
    )
    assert set(result.values) == {"lat", "lon"}


def test_freeze_non_finite_active_rows_raise() -> None:
    with pytest.raises(ValueError, match="NaN|inf"):
        freeze_lat_lon(
            np.array([np.nan]), np.array([10.0]), np.array([1.0]), 41.0, 11.0
        )


def test_freeze_does_not_mutate_inputs_and_is_deterministic() -> None:
    lat = np.array([40.0, 41.0, 42.0])
    lon = np.array([10.0, 11.0, 12.0])
    a = np.array([0.0, 0.5, 1.0])
    snapshots = [lat.copy(), lon.copy(), a.copy()]

    first = freeze_lat_lon(lat, lon, a, 50.0, 60.0)
    second = freeze_lat_lon(lat, lon, a, 50.0, 60.0)

    for current, snapshot in zip([lat, lon, a], snapshots):
        assert_same(current, snapshot)
    assert_same(first.values["lat"], second.values["lat"])
    assert_same(first.values["lon"], second.values["lon"])


def test_anchor_is_the_last_eligible_row_strictly_before_start() -> None:
    lat = np.array([40.0, 41.0, 42.0, 43.0])
    lon = np.array([10.0, 11.0, 12.0, 13.0])
    eligible = np.array([True, True, True, True])
    times = np.array([0.0, 10.0, 20.0, 30.0])

    anchor = anchor_from_offsets(lat, lon, eligible, 3, times)
    assert anchor == (42.0, 12.0)


def test_anchor_skips_ineligible_rows() -> None:
    lat = np.array([40.0, 41.0, 42.0, 43.0])
    lon = np.array([10.0, 11.0, 12.0, 13.0])
    eligible = np.array([True, False, False, True])
    times = np.array([0.0, 10.0, 20.0, 30.0])

    assert anchor_from_offsets(lat, lon, eligible, 3, times) == (40.0, 10.0)


def test_anchor_too_old_returns_none() -> None:
    lat = np.array([40.0, 41.0, 42.0, 43.0])
    lon = np.array([10.0, 11.0, 12.0, 13.0])
    eligible = np.array([True, False, False, True])
    times = np.array([0.0, 10.0, 20.0, 100.0])

    assert anchor_from_offsets(lat, lon, eligible, 3, times) is None
    assert anchor_from_offsets(
        lat, lon, eligible, 3, times, max_anchor_age_seconds=100.0
    ) == (40.0, 10.0)


def test_anchor_age_limit_is_inclusive() -> None:
    lat = np.array([40.0, 41.0, 42.0, 43.0])
    lon = np.array([10.0, 11.0, 12.0, 13.0])
    eligible = np.array([True, False, False, True])
    times = np.array([0.0, 10.0, 20.0, 30.0])

    assert anchor_from_offsets(
        lat, lon, eligible, 3, times, max_anchor_age_seconds=30.0
    ) == (40.0, 10.0)


def test_anchor_missing_returns_none() -> None:
    lat = np.array([40.0, 41.0])
    lon = np.array([10.0, 11.0])
    times = np.array([0.0, 10.0])

    assert anchor_from_offsets(
        lat, lon, np.array([True, True]), 0, times
    ) is None
    assert anchor_from_offsets(
        lat, lon, np.array([False, False]), 1, times
    ) is None


def test_anchor_skips_non_finite_values() -> None:
    lat = np.array([np.nan, 41.0, 42.0, 43.0])
    lon = np.array([10.0, 11.0, 12.0, 13.0])
    eligible = np.array([True, True, True, True])
    times = np.array([0.0, 10.0, 20.0, 30.0])

    assert anchor_from_offsets(lat, lon, eligible, 3, times) == (42.0, 12.0)


def test_anchor_validates_arguments() -> None:
    lat = np.array([40.0, 41.0])
    lon = np.array([10.0, 11.0])
    eligible = np.array([True, True])
    times = np.array([0.0, 10.0])

    with pytest.raises(ValueError, match="start_offset"):
        anchor_from_offsets(lat, lon, eligible, 2, times)
    with pytest.raises(ValueError, match="max_anchor_age"):
        anchor_from_offsets(
            lat, lon, eligible, 1, times, max_anchor_age_seconds=-1.0
        )
