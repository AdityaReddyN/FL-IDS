"""Episode builder tests (D-024)."""

import numpy as np
import pytest

from flids.attacks.detectability import injected_displacement_m
from flids.attacks.episode import (
    MIN_EFFECTIVE_ROWS,
    NOOP_MIN_ALTITUDE_M,
    NOOP_MIN_HORIZONTAL_M,
    EpisodeSpec,
    build_episode,
)
from flids.attacks.manipulation import (
    add_scaled_eq12_noise,
    apply_horizontal_displacement,
    horizontal_displacement_gaussian,
    manipulation_streams,
)
from flids.attacks.ramps import ramp_multipliers


def moving_segment(n_rows: int = 120) -> dict[str, np.ndarray]:
    index = np.arange(n_rows, dtype=float)
    return {
        "lat": 40.0 + 0.001 * index,
        "lon": 10.0 + 0.001 * index,
        "velocity": 200.0 + index,
        "heading": (5.0 * index) % 360.0,
        "vertrate": 0.1 * index,
        "baroaltitude": 3000.0 + index,
        "geoaltitude": 3010.0 + index,
        "onground": np.zeros(n_rows, dtype=bool),
        "contact_lag_seconds": np.zeros(n_rows),
        "contact_lag_missing": np.zeros(n_rows, dtype=bool),
        "lat_missing": np.zeros(n_rows, dtype=bool),
        "lon_missing": np.zeros(n_rows, dtype=bool),
    }


def stationary_segment(n_rows: int = 120) -> dict[str, np.ndarray]:
    values = moving_segment(n_rows)
    for name in (
        "lat", "lon", "velocity", "heading", "vertrate",
        "baroaltitude", "geoaltitude",
    ):
        values[name] = np.full(n_rows, values[name][0])
    values["velocity"] = np.zeros(n_rows)
    return values


def spec(family: str, **overrides) -> EpisodeSpec:
    parameters = {"attack_family": family, "tier": "moderate"}
    parameters.update(overrides)
    return EpisodeSpec(**parameters)


def build(segment, times, start, n_rows, episode_spec, *,
          eligible=None, sources=None, seed=7):
    if eligible is None:
        eligible = np.ones(len(times), dtype=bool)
    return build_episode(
        segment,
        times,
        eligible,
        sources,
        start,
        n_rows,
        episode_spec,
        np.random.default_rng(seed),
    )


def assert_same(first, second) -> None:
    assert np.array_equal(
        np.asarray(first), np.asarray(second), equal_nan=True
    )


def test_constant_episode_end_to_end() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    result = build(
        segment, times, 10, 20,
        spec("constant_deviation", magnitude_m=5000.0, bearing_deg=45.0),
    )

    assert result.accepted, result.reason
    assert result.start_offset == 10
    assert result.n_rows == 20
    assert result.delays is None
    multipliers, positions = ramp_multipliers(20, 3, "linear_mix")
    assert_same(result.multipliers, multipliers)
    assert positions.tolist() == result.positions.tolist()

    measured = injected_displacement_m(
        segment["lat"][10:30], segment["lon"][10:30],
        result.values["lat"], result.values["lon"],
    )
    assert np.allclose(measured, 5000.0 * multipliers, atol=0.1)
    assert result.horizontal_displacement_m.tolist() == pytest.approx(
        (5000.0 * multipliers).tolist(), abs=0.1
    )
    assert result.altitude_change_m.tolist() == [0.0] * 20
    assert result.summary["n_effective_rows"] == 18
    for row in range(20):
        assert result.changed_fields[row] == ("lat", "lon")


def test_build_episode_rejects_ineligible_interval() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    eligible = np.ones(120, dtype=bool)
    eligible[15] = False
    result = build(
        segment, times, 10, 20,
        spec("constant_deviation", magnitude_m=5000.0, bearing_deg=45.0),
        eligible=eligible,
    )
    assert not result.accepted
    assert result.reason == "ineligible_interval"
    assert_same(result.values["lat"], segment["lat"][10:30])


def test_baro_only_episode_does_not_require_geoaltitude() -> None:
    segment = moving_segment()
    del segment["geoaltitude"]
    times = np.arange(120) * 10
    result = build(
        segment, times, 10, 20,
        spec(
            "altitude_constant_deviation",
            altitude_variant="baro_only",
            shift_m=125.0,
        ),
    )
    assert result.accepted, result.reason
    assert set(result.values) == {"baroaltitude"}


def test_gradual_episode_end_to_end() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    result = build(
        segment, times, 0, 60,
        spec("gradual_deviation", magnitude_m=6000.0, bearing_deg=123.0),
    )
    assert result.accepted, result.reason

    g = np.arange(60, dtype=float) / 59
    multipliers, _ = ramp_multipliers(60, 3, "linear_mix")
    realized = multipliers * g
    assert_same(result.multipliers, realized)
    assert result.summary["n_effective_rows"] == 28

    measured = injected_displacement_m(
        segment["lat"][:60], segment["lon"][:60],
        result.values["lat"], result.values["lon"],
    )
    assert np.allclose(measured, 6000.0 * realized, atol=0.1)
    assert result.values["lat"][0] == segment["lat"][0]
    assert result.changed_fields[0] == ()


def test_gaussian_with_eq12_equals_manual_composition() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    episode_spec = spec(
        "random_gaussian_deviation",
        sigma_m=250.0,
        kappa=0.2,
        per_step_sigma_m=25.0,
    )
    result = build(
        segment, times, 20, 30, episode_spec, seed=99
    )
    assert result.accepted, result.reason

    multipliers, _ = ramp_multipliers(30, 3, "linear_mix")
    gaussian_rng, noise_rng = manipulation_streams(
        np.random.default_rng(99)
    )
    north, east = horizontal_displacement_gaussian(
        multipliers, 250.0, gaussian_rng
    )
    north, east = add_scaled_eq12_noise(
        north, east, multipliers, 0.2, 25.0, noise_rng
    )
    manual = apply_horizontal_displacement(
        segment["lat"][20:50], segment["lon"][20:50],
        multipliers, north, east,
    )
    assert_same(result.values["lat"], manual.values["lat"])
    assert_same(result.values["lon"], manual.values["lon"])
    assert not np.array_equal(
        result.values["lat"],
        apply_horizontal_displacement(
            segment["lat"][20:50],
            segment["lon"][20:50],
            multipliers,
            *horizontal_displacement_gaussian(
                multipliers, 250.0,
                manipulation_streams(np.random.default_rng(99))[0],
            ),
        ).values["lat"],
    )


def test_altitude_variants_end_to_end() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    multipliers, _ = ramp_multipliers(20, 3, "linear_mix")

    baro_only = build(
        segment, times, 10, 20,
        spec(
            "altitude_constant_deviation",
            shift_m=125.0,
            altitude_variant="baro_only",
        ),
    )
    assert baro_only.accepted, baro_only.reason
    assert_same(
        baro_only.values["baroaltitude"],
        segment["baroaltitude"][10:30] + 125.0 * multipliers,
    )
    assert "geoaltitude" not in baro_only.values

    both = build(
        segment, times, 10, 20,
        spec(
            "altitude_constant_deviation",
            shift_m=125.0,
            altitude_variant="baro_plus_geo",
        ),
    )
    assert both.accepted, both.reason
    assert_same(
        both.values["geoaltitude"],
        segment["geoaltitude"][10:30] + 125.0 * multipliers,
    )


def test_replay_partial_and_full_read_original_sources() -> None:
    segment = moving_segment()
    originals = {name: array.copy() for name, array in segment.items()}
    times = np.arange(120) * 10
    sources = np.full(120, -1, dtype=np.int64)
    sources[30:90] = np.arange(0, 60)

    partial = build(
        segment, times, 30, 60, spec("replay_partial_field"), sources=sources
    )
    assert partial.accepted, partial.reason
    assert partial.delays[0] == 300.0 and partial.delays[-1] == 300.0
    for row in range(60):
        source_row = 30 + row - 30
        if partial.multipliers[row] == 1.0:
            assert partial.values["lat"][row] == pytest.approx(
                originals["lat"][source_row], abs=1e-9
            )
            assert partial.values["lon"][row] == pytest.approx(
                originals["lon"][source_row], abs=1e-9
            )
            assert partial.values["baroaltitude"][row] == pytest.approx(
                originals["baroaltitude"][source_row], abs=1e-9
            )
    assert partial.values["lat"][0] == pytest.approx(
        0.75 * originals["lat"][30] + 0.25 * originals["lat"][0],
        abs=1e-9,
    )
    for name in ("velocity", "heading", "vertrate", "geoaltitude"):
        assert name not in partial.values

    full = build(
        segment, times, 30, 60, spec("replay_full_field"), sources=sources
    )
    assert full.accepted, full.reason
    for name in (
        "lat", "lon", "velocity", "heading", "vertrate",
        "baroaltitude", "geoaltitude",
    ):
        for row in range(60):
            if full.multipliers[row] == 1.0:
                assert full.values[name][row] == pytest.approx(
                    originals[name][30 + row - 30], abs=1e-9
                )
    assert np.all(full.altitude_change_m >= 0.0)


def test_freeze_holds_the_anchor() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    eligible = np.ones(120, dtype=bool)
    result = build(
        segment, times, 10, 20, spec("freeze_fixed_value"),
        eligible=eligible,
    )
    assert result.accepted, result.reason
    anchor_lat = segment["lat"][9]
    anchor_lon = segment["lon"][9]
    interior = result.positions == "interior"
    assert np.allclose(result.values["lat"][interior], anchor_lat)
    assert np.allclose(result.values["lon"][interior], anchor_lon)
    assert set(result.values) == {"lat", "lon"}
    assert result.altitude_change_m.tolist() == [0.0] * 20
    assert result.anchor_offset == 9


def test_latitude_and_altitude_out_of_range_rejections() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    segment["lat"] = np.full(120, 89.999)
    rejected = build(
        segment, times, 10, 20,
        spec("constant_deviation", magnitude_m=11000.0, bearing_deg=0.0),
    )
    assert not rejected.accepted
    assert rejected.reason == "latitude_out_of_range"

    segment = moving_segment()
    segment["baroaltitude"] = np.full(120, 19_990.0)
    rejected = build(
        segment, times, 10, 20,
        spec(
            "altitude_constant_deviation",
            shift_m=500.0,
            altitude_variant="baro_only",
        ),
    )
    assert not rejected.accepted
    assert rejected.reason == "altitude_out_of_range"


def test_missing_replay_source_rejects_as_defensive_guard() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    sources = np.full(120, -1, dtype=np.int64)
    sources[30:90] = np.arange(0, 60)
    sources[45] = -1

    result = build(
        segment, times, 30, 60, spec("replay_partial_field"), sources=sources
    )
    assert not result.accepted
    assert result.reason == "no_replay_source"


def test_missing_freeze_anchor_rejects() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    result = build(
        segment, times, 0, 20, spec("freeze_fixed_value")
    )
    assert not result.accepted
    assert result.reason == "no_freeze_anchor"


def test_insufficient_effective_rows_rejects_gradual() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    result = build(
        segment, times, 0, 12,
        spec("gradual_deviation", magnitude_m=6000.0, bearing_deg=90.0),
    )
    assert not result.accepted
    assert result.reason == "insufficient_effective_rows"
    assert MIN_EFFECTIVE_ROWS == 5


def test_replay_delay_mismatch_rejects() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    sources = np.full(120, -1, dtype=np.int64)
    sources[30:90] = np.arange(25, 85)  # a 50 s delay, not 300 s

    result = build(
        segment, times, 30, 60, spec("replay_partial_field"), sources=sources
    )
    assert not result.accepted
    assert result.reason == "replay_delay_mismatch"


def test_no_measurable_change_guard() -> None:
    times = np.arange(120) * 10

    stationary = stationary_segment()
    freeze = build(
        stationary, times, 10, 20, spec("freeze_fixed_value")
    )
    assert not freeze.accepted
    assert freeze.reason == "no_measurable_change"
    assert NOOP_MIN_HORIZONTAL_M == 100.0

    sources = np.full(120, -1, dtype=np.int64)
    sources[30:90] = np.arange(0, 60)
    identical = build(
        stationary, times, 30, 60,
        spec("replay_partial_field"), sources=sources,
    )
    assert not identical.accepted
    assert identical.reason == "no_measurable_change"
    assert NOOP_MIN_ALTITUDE_M == 30.0

    small_shift = build(
        moving_segment(), times, 10, 20,
        spec(
            "altitude_constant_deviation",
            shift_m=29.9,
            altitude_variant="baro_only",
        ),
    )
    assert not small_shift.accepted
    assert small_shift.reason == "no_measurable_change"


def test_replay_full_without_position_or_altitude_change_is_noop() -> None:
    segment = moving_segment()
    for name in ("lat", "lon", "baroaltitude", "geoaltitude"):
        segment[name] = np.full(120, segment[name][0])
    times = np.arange(120) * 10
    sources = np.full(120, -1, dtype=np.int64)
    sources[30:90] = np.arange(0, 60)

    result = build(
        segment, times, 30, 60, spec("replay_full_field"), sources=sources
    )
    assert not result.accepted
    assert result.reason == "no_measurable_change"


def test_builder_inputs_are_not_mutated_and_metadata_is_untouched() -> None:
    segment = moving_segment()
    snapshots = {name: array.copy() for name, array in segment.items()}
    times = np.arange(120) * 10
    eligible = np.ones(120, dtype=bool)
    sources = np.full(120, -1, dtype=np.int64)
    sources[30:90] = np.arange(0, 60)

    result = build(
        segment, times, 30, 60,
        spec("replay_partial_field"), eligible=eligible, sources=sources,
    )
    assert result.accepted, result.reason
    for name, snapshot in snapshots.items():
        assert_same(segment[name], snapshot)
    assert_same(eligible, np.ones(120, dtype=bool))
    assert sources[90] == -1
    metadata = {
        "onground", "contact_lag_seconds", "contact_lag_missing",
        "lat_missing", "lon_missing",
    }
    assert not metadata & set(result.values)


def test_builder_is_deterministic_for_the_same_seed() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    episode_spec = spec(
        "random_gaussian_deviation", sigma_m=250.0, kappa=0.2
    )
    first = build(segment, times, 20, 30, episode_spec, seed=123)
    second = build(segment, times, 20, 30, episode_spec, seed=123)
    other = build(segment, times, 20, 30, episode_spec, seed=124)

    assert first.accepted and second.accepted and other.accepted
    assert_same(first.values["lat"], second.values["lat"])
    assert_same(first.values["lon"], second.values["lon"])
    assert not np.array_equal(first.values["lat"], other.values["lat"])


def test_invalid_specification_raises() -> None:
    segment = moving_segment()
    times = np.arange(120) * 10
    with pytest.raises(ValueError, match="attack_family"):
        build(segment, times, 10, 20, spec("not_a_family"))
    with pytest.raises(ValueError, match="onset_mode"):
        build(
            segment, times, 10, 20,
            spec("constant_deviation", onset_mode="bogus"),
        )
    with pytest.raises(ValueError, match="magnitude_m"):
        build(segment, times, 10, 20, spec("constant_deviation"))
    with pytest.raises(ValueError, match="altitude_variant"):
        build(
            segment, times, 10, 20,
            spec("altitude_constant_deviation", shift_m=125.0),
        )
