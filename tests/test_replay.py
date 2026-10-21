"""Replay primitives: original-array sources, delays, and blending (D-023)."""

import numpy as np
import pytest

from flids.attacks.replay import (
    FULL_REPLAY_FIELDS,
    PARTIAL_REPLAY_FIELDS,
    replay_fields,
)


def make_values(n_rows: int) -> dict[str, np.ndarray]:
    index = np.arange(n_rows, dtype=float)
    return {
        "lat": 40.0 + 0.001 * index,
        "lon": 10.0 + 0.001 * index,
        "velocity": 100.0 + index,
        "heading": (5.0 * index) % 360.0,
        "vertrate": 0.1 * index,
        "baroaltitude": 3000.0 + index,
        "geoaltitude": 3010.0 + index,
    }


def assert_same(first, second) -> None:
    assert np.array_equal(
        np.asarray(first), np.asarray(second), equal_nan=True
    )


def test_partial_and_full_field_sets() -> None:
    assert PARTIAL_REPLAY_FIELDS == ("lat", "lon", "baroaltitude")
    assert FULL_REPLAY_FIELDS == (
        "lat",
        "lon",
        "velocity",
        "heading",
        "vertrate",
        "baroaltitude",
        "geoaltitude",
    )


def test_exact_sources_and_achieved_delays() -> None:
    values = make_values(5)
    times = np.array([0, 10, 20, 30, 40], dtype=np.int64)
    sources = np.array([-1, -1, 0, 1, 2], dtype=np.int64)
    a = np.array([0.0, 0.0, 1.0, 1.0, 1.0])

    result = replay_fields(values, sources, a, ("lat",), times)
    assert not result.rejected
    assert np.isnan(result.delays[0]) and np.isnan(result.delays[1])
    assert result.delays[2:].tolist() == [20.0, 20.0, 20.0]
    assert result.values["lat"][2] == values["lat"][0]
    assert result.values["lat"][3] == values["lat"][1]
    assert result.values["lat"][4] == values["lat"][2]
    assert_same(result.values["lat"][:2], values["lat"][:2])


def test_long_episode_sources_inside_the_episode_read_original_values() -> None:
    n_rows = 60
    values = make_values(n_rows)
    originals = {name: array.copy() for name, array in values.items()}
    times = np.arange(n_rows, dtype=np.int64) * 10
    sources = np.concatenate(
        (-np.ones(30, dtype=np.int64), np.arange(30, dtype=np.int64))
    )
    a = np.concatenate((np.zeros(30), np.ones(30)))

    result = replay_fields(values, sources, a, FULL_REPLAY_FIELDS, times)
    assert not result.rejected
    for i in range(30, n_rows):
        assert result.delays[i] == 300.0
        for name in FULL_REPLAY_FIELDS:
            assert result.values[name][i] == pytest.approx(
                originals[name][i - 30], abs=1e-9
            )


def test_source_inside_active_region_reads_original_not_replayed() -> None:
    # Delay 10 rows: sources of rows 10..59 include rows 10..49, which are
    # themselves replayed. An in-place implementation would chain the values.
    n_rows = 60
    values = make_values(n_rows)
    originals = {name: array.copy() for name, array in values.items()}
    times = np.arange(n_rows, dtype=np.int64) * 10
    sources = np.concatenate(
        (-np.ones(10, dtype=np.int64), np.arange(50, dtype=np.int64))
    )
    a = np.concatenate((np.zeros(10), np.ones(50)))

    result = replay_fields(values, sources, a, ("lat", "lon"), times)
    assert not result.rejected
    for i in range(10, n_rows):
        assert result.values["lat"][i] == pytest.approx(
            originals["lat"][i - 10], abs=1e-9
        )
        assert result.values["lon"][i] == pytest.approx(
            originals["lon"][i - 10], abs=1e-9
        )


def test_ramp_row_blends_current_and_source() -> None:
    values = {
        "lat": np.array([100.0, 200.0]),
        "lon": np.array([10.0, 20.0]),
    }
    times = np.array([0, 10], dtype=np.int64)
    sources = np.array([-1, 0], dtype=np.int64)
    a = np.array([0.0, 0.25])

    result = replay_fields(values, sources, a, ("lat",), times)
    assert not result.rejected
    assert result.values["lat"][1] == 175.0
    assert result.values["lat"][0] == 100.0


def test_heading_blends_across_the_shortest_arc() -> None:
    values = {"heading": np.array([10.0, 350.0])}
    times = np.array([0, 10], dtype=np.int64)
    sources = np.array([-1, 0], dtype=np.int64)
    a = np.array([0.0, 0.5])

    result = replay_fields(values, sources, a, ("heading",), times)
    assert not result.rejected
    assert result.values["heading"][1] == pytest.approx(0.0, abs=1e-12)
    assert 0.0 <= result.values["heading"][1] < 360.0


def test_partial_replay_leaves_other_fields_bit_identical() -> None:
    n_rows = 5
    values = make_values(n_rows)
    times = np.arange(n_rows, dtype=np.int64) * 10
    sources = np.array([-1, -1, 0, 1, 2], dtype=np.int64)
    a = np.array([0.0, 0.0, 1.0, 1.0, 1.0])
    originals = {name: array.copy() for name, array in values.items()}

    result = replay_fields(values, sources, a, PARTIAL_REPLAY_FIELDS, times)
    assert not result.rejected
    for name in ("velocity", "heading", "vertrate", "geoaltitude"):
        assert_same(result.values[name], originals[name])
    for name in PARTIAL_REPLAY_FIELDS:
        assert not np.array_equal(
            result.values[name][2:], originals[name][2:]
        )


def test_full_replay_changes_all_seven_when_sources_differ() -> None:
    n_rows = 5
    values = make_values(n_rows)
    times = np.arange(n_rows, dtype=np.int64) * 10
    sources = np.array([-1, -1, 0, 1, 2], dtype=np.int64)
    a = np.array([0.0, 0.0, 1.0, 1.0, 1.0])
    originals = {name: array.copy() for name, array in values.items()}

    result = replay_fields(values, sources, a, FULL_REPLAY_FIELDS, times)
    assert not result.rejected
    for name in FULL_REPLAY_FIELDS:
        assert result.values[name][2] != originals[name][2]
        assert result.values[name][2] == pytest.approx(
            originals[name][0], abs=1e-9
        )


def circular_distance_degrees(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def test_longitude_blend_crosses_the_antimeridian() -> None:
    times = np.array([0, 10], dtype=np.int64)
    sources = np.array([-1, 0], dtype=np.int64)
    a = np.array([0.0, 0.5])

    eastward = replay_fields(
        {"lon": np.array([-179.9, 179.9])}, sources, a, ("lon",), times
    )
    assert circular_distance_degrees(
        float(eastward.values["lon"][1]), -180.0
    ) < 1e-9
    assert -180.0 <= eastward.values["lon"][1] < 180.0

    westward = replay_fields(
        {"lon": np.array([179.9, -179.9])}, sources, a, ("lon",), times
    )
    assert circular_distance_degrees(
        float(westward.values["lon"][1]), -180.0
    ) < 1e-9
    assert -180.0 <= westward.values["lon"][1] < 180.0


def test_active_row_with_no_source_rejects_the_whole_episode() -> None:
    values = make_values(3)
    originals = {name: array.copy() for name, array in values.items()}
    times = np.array([0, 10, 20], dtype=np.int64)
    sources = np.array([-1, 0, -1], dtype=np.int64)
    a = np.array([1.0, 1.0, 1.0])

    result = replay_fields(values, sources, a, ("lat",), times)
    assert result.rejected
    assert result.reason == "no_replay_source"
    for name in values:
        assert_same(result.values[name], originals[name])
    assert np.isnan(result.delays).all()


@pytest.mark.parametrize("bad_source", [1, 2, -2])
def test_active_source_not_strictly_before_target_raises(
    bad_source: int,
) -> None:
    values = {"lat": np.array([10.0, 20.0])}
    times = np.array([0, 10], dtype=np.int64)
    sources = np.array([-1, bad_source], dtype=np.int64)
    a = np.array([0.0, 1.0])

    with pytest.raises(ValueError, match="source"):
        replay_fields(values, sources, a, ("lat",), times)


def test_non_finite_source_value_raises() -> None:
    values = {
        "lat": np.array([10.0, 20.0]),
        "velocity": np.array([np.nan, 120.0]),
    }
    times = np.array([0, 10], dtype=np.int64)
    sources = np.array([-1, 0], dtype=np.int64)
    a = np.array([0.0, 1.0])

    with pytest.raises(ValueError, match="finite|NaN"):
        replay_fields(values, sources, a, ("velocity",), times)


def test_unknown_or_missing_fields_raise() -> None:
    values = {"lat": np.array([10.0, 20.0])}
    times = np.array([0, 10], dtype=np.int64)
    sources = np.array([-1, 0], dtype=np.int64)
    a = np.array([0.0, 1.0])

    with pytest.raises(ValueError, match="allowed"):
        replay_fields(values, sources, a, ("onground",), times)
    with pytest.raises(KeyError, match="geoaltitude"):
        replay_fields(values, sources, a, ("geoaltitude",), times)


def test_inactive_rows_and_unlisted_fields_are_bit_identical() -> None:
    values = {
        "lat": np.array([10.0, 20.0]),
        "geoaltitude": np.array([np.nan, 3010.0]),
    }
    times = np.array([0, 10], dtype=np.int64)
    sources = np.array([-1, 0], dtype=np.int64)
    a = np.array([0.0, 1.0])

    result = replay_fields(values, sources, a, ("lat",), times)
    assert result.values["lat"][0] == 10.0
    assert_same(result.values["geoaltitude"], values["geoaltitude"])


def test_replay_does_not_mutate_inputs_and_is_deterministic() -> None:
    values = make_values(60)
    snapshots = {name: array.copy() for name, array in values.items()}
    times = np.arange(60, dtype=np.int64) * 10
    sources = np.concatenate(
        (-np.ones(30, dtype=np.int64), np.arange(30, dtype=np.int64))
    )
    a = np.concatenate((np.zeros(30), np.ones(30)))
    sources_snapshot = sources.copy()
    a_snapshot = a.copy()

    first = replay_fields(values, sources, a, FULL_REPLAY_FIELDS, times)
    second = replay_fields(values, sources, a, FULL_REPLAY_FIELDS, times)

    for name in values:
        assert_same(values[name], snapshots[name])
        assert_same(first.values[name], second.values[name])
    assert_same(sources, sources_snapshot)
    assert_same(a, a_snapshot)
    assert_same(first.delays, second.delays)
