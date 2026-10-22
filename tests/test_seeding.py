import numpy as np
import pytest

from flids.attacks.seeding import (
    episode_rng,
    episode_seed_sequence,
    parameter_rng,
    parameter_seed_sequence,
    placement_rng,
    overlay_selection_rng,
    segment_rng,
    segment_seed_sequence,
)


def draws(rng: np.random.Generator, count: int = 8) -> np.ndarray:
    return rng.random(count)


def test_segment_rng_is_deterministic() -> None:
    assert np.array_equal(
        draws(segment_rng(42, "abc123", 7)),
        draws(segment_rng(42, "abc123", 7)),
    )


def test_different_global_seeds_give_different_draws() -> None:
    assert not np.array_equal(
        draws(segment_rng(42, "abc123", 7)),
        draws(segment_rng(43, "abc123", 7)),
    )


def test_different_segments_give_different_draws() -> None:
    assert not np.array_equal(
        draws(segment_rng(42, "abc123", 7)),
        draws(segment_rng(42, "abc123", 8)),
    )


def test_other_segment_draws_do_not_change_this_segment() -> None:
    before = draws(segment_rng(42, "abc123", 7))
    for other in range(5):
        draws(segment_rng(42, "other", other))
    after = draws(segment_rng(42, "abc123", 7))
    assert np.array_equal(before, after)


def test_episode_rng_is_deterministic() -> None:
    assert np.array_equal(
        draws(episode_rng(42, "abc123", 7, 2)),
        draws(episode_rng(42, "abc123", 7, 2)),
    )


def test_episode_rng_does_not_depend_on_other_episodes() -> None:
    alone = draws(episode_rng(42, "abc123", 7, 3))
    for index in range(10):
        draws(episode_rng(42, "abc123", 7, index))
    after = draws(episode_rng(42, "abc123", 7, 3))
    assert np.array_equal(alone, after)


def test_episode_rng_uses_episode_index_as_spawn_key() -> None:
    assert episode_seed_sequence(42, "abc123", 7, 3).spawn_key == (3,)


def test_episode_rng_differs_from_segment_rng_and_other_episodes() -> None:
    assert not np.array_equal(
        draws(episode_rng(42, "abc123", 7, 0)),
        draws(episode_rng(42, "abc123", 7, 1)),
    )
    assert not np.array_equal(
        draws(episode_rng(42, "abc123", 7, 0)),
        draws(segment_rng(42, "abc123", 7)),
    )


def test_parameter_rng_isolated_from_episode_and_other_episodes() -> None:
    assert parameter_seed_sequence(42, "abc123", 7, 3).spawn_key == (3,)
    assert not np.array_equal(
        draws(parameter_rng(42, "abc123", 7, 3)),
        draws(episode_rng(42, "abc123", 7, 3)),
    )


def test_named_streams_have_fixed_distinct_first_draws() -> None:
    streams = (segment_rng(42, "abc123", 7), episode_rng(42, "abc123", 7, 2), parameter_rng(42, "abc123", 7, 2), placement_rng(42, "abc123", 7, 2))
    values = [float(stream.random()) for stream in streams]
    assert values == [0.8364815163664566, 0.7922062726451717, 0.3935657176777222, 0.9296434393963378]
    assert len(set(values)) == 4
    assert not np.array_equal(
        draws(parameter_rng(42, "abc123", 7, 3)),
        draws(parameter_rng(42, "abc123", 7, 4)),
    )


def test_overlay_selection_streams_are_independent_and_deterministic() -> None:
    constant = overlay_selection_rng(42, "abc123", 7, "constant_deviation|moderate")
    gaussian = overlay_selection_rng(42, "abc123", 7, "random_gaussian_deviation|moderate")
    again = overlay_selection_rng(42, "abc123", 7, "constant_deviation|moderate")
    assert constant.random() != gaussian.random()
    assert overlay_selection_rng(42, "abc123", 7, "constant_deviation|moderate").random() == again.random()


def test_negative_episode_index_raises() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        episode_rng(42, "abc123", 7, -1)


def test_segment_id_is_coerced_to_int() -> None:
    assert np.array_equal(
        draws(segment_rng(42, "abc123", 7.0)),
        draws(segment_rng(42, "abc123", 7)),
    )
    assert np.array_equal(
        draws(episode_rng(42, "abc123", np.int64(7), 0)),
        draws(episode_rng(42, "abc123", 7, 0)),
    )
