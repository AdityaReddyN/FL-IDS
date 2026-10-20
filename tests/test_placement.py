import numpy as np
import pytest

from flids.attacks.placement import (
    MAX_SPAN_FACTOR,
    MIN_SPAN_FACTOR,
    filter_starts_by_span,
    place_episodes,
)


def regular_times(n: int, step: int = 10) -> np.ndarray:
    return np.arange(n, dtype=np.int64) * step


def seeded(k: int) -> np.random.Generator:
    return np.random.default_rng(10_000 + k)


class AscendingGenerator:
    """Deterministic stand-in for a Generator; picks the earliest candidate."""

    def permutation(self, values):
        return np.sort(np.asarray(values))


class FirstValueGenerator:
    """Deterministic stand-in that puts a chosen start first when available."""

    def __init__(self, first: int):
        self.first = first

    def permutation(self, values):
        values = np.asarray(values)
        if np.any(values == self.first):
            rest = values[values != self.first]
            return np.concatenate(([self.first], np.sort(rest)))
        return np.sort(values)


def test_span_filter_constants_are_named_and_provisional() -> None:
    assert MIN_SPAN_FACTOR == 0.8
    assert MAX_SPAN_FACTOR == 1.25


def test_filter_starts_by_span_keeps_and_removes() -> None:
    regular = regular_times(20)
    kept, removed = filter_starts_by_span(
        np.arange(9, dtype=np.int64), regular, 12, 120
    )
    assert kept.tolist() == list(range(9))
    assert removed == 0

    irregular = np.array(
        [0, 10, 20, 30, 40, 140, 150, 160, 170, 180, 190, 200],
        dtype=np.int64,
    )
    kept, removed = filter_starts_by_span(
        np.array([0], dtype=np.int64), irregular, 12, 120
    )
    assert kept.tolist() == []
    assert removed == 1


def test_n_rows_uses_floor_divide() -> None:
    times = regular_times(100)
    accepted, rejected = place_episodes(
        np.array([0], dtype=np.int64), times, 125, 1, seeded
    )
    assert accepted == [(0, 12)]
    assert rejected == []


def test_segment_too_short_rejects_every_request() -> None:
    times = regular_times(5)
    accepted, rejected = place_episodes(
        np.array([0], dtype=np.int64), times, 120, 2, seeded
    )
    assert accepted == []
    assert rejected == [(0, "segment_too_short"), (1, "segment_too_short")]


def test_no_eligible_start_rejects_every_request() -> None:
    times = regular_times(20)
    accepted, rejected = place_episodes(
        np.array([], dtype=np.int64), times, 120, 2, seeded
    )
    assert accepted == []
    assert rejected == [(0, "no_eligible_start"), (1, "no_eligible_start")]


def test_span_filtered_start_is_not_placed() -> None:
    irregular = np.array(
        [0, 10, 20, 30, 40, 140, 150, 160, 170, 180, 190, 200],
        dtype=np.int64,
    )
    accepted, rejected = place_episodes(
        np.array([0], dtype=np.int64), irregular, 120, 2, seeded
    )
    assert accepted == []
    assert rejected == [(0, "no_eligible_start"), (1, "no_eligible_start")]


def test_gap_violation_and_rejected_starts_stay_available() -> None:
    times = regular_times(100)
    valid = np.arange(100 - 12 + 1, dtype=np.int64)
    accepted, rejected = place_episodes(
        valid,
        times,
        120,
        3,
        lambda _k: AscendingGenerator(),
        min_gap_seconds=600.0,
    )
    assert accepted == [(0, 12), (71, 12)]
    assert rejected == [(2, "gap_violation")]


def test_max_per_segment_is_enforced() -> None:
    times = regular_times(400)
    valid = np.arange(400 - 12 + 1, dtype=np.int64)
    accepted, rejected = place_episodes(
        valid,
        times,
        120,
        5,
        seeded,
        max_per_segment=2,
        min_gap_seconds=600.0,
    )
    assert len(accepted) == 2
    assert rejected == [
        (2, "max_per_segment_exceeded"),
        (3, "max_per_segment_exceeded"),
        (4, "max_per_segment_exceeded"),
    ]


def test_accepted_windows_do_not_overlap() -> None:
    times = regular_times(400)
    valid = np.arange(400 - 12 + 1, dtype=np.int64)
    accepted, _ = place_episodes(valid, times, 120, 3, seeded)
    windows = [(start, start + n_rows) for start, n_rows in accepted]
    for i, (a_start, a_end) in enumerate(windows):
        for b_start, b_end in windows[i + 1 :]:
            assert a_end <= b_start or b_end <= a_start


def test_per_request_generator_controls_selection() -> None:
    times = regular_times(400)
    valid = np.arange(400 - 12 + 1, dtype=np.int64)
    calls: list[int] = []

    def rng_for_request(k: int):
        calls.append(k)
        return FirstValueGenerator(5)

    accepted, rejected = place_episodes(
        valid, times, 120, 2, rng_for_request, min_gap_seconds=600.0
    )
    assert calls == [0, 1]
    assert accepted[0] == (5, 12)
    assert rejected == []


def test_later_request_does_not_change_earlier_placement() -> None:
    times = regular_times(500)
    valid = np.arange(500 - 12 + 1, dtype=np.int64)
    short, short_rejected = place_episodes(valid, times, 120, 3, seeded)
    long, long_rejected = place_episodes(valid, times, 120, 5, seeded)
    assert long[: len(short)] == short
    assert long_rejected[: len(short_rejected)] == short_rejected


def test_requests_are_fully_accounted_for() -> None:
    times = regular_times(200)
    valid = np.arange(200 - 12 + 1, dtype=np.int64)
    n_requested = 5
    accepted, rejected = place_episodes(
        valid, times, 120, n_requested, seeded, max_per_segment=2
    )
    rejected_indices = {index for index, _ in rejected}
    accepted_indices = sorted(set(range(n_requested)) - rejected_indices)
    assert len(accepted) == len(accepted_indices)
    assert len(accepted) + len(rejected) == n_requested


def test_zero_requests_is_empty() -> None:
    times = regular_times(100)
    accepted, rejected = place_episodes(
        np.arange(89, dtype=np.int64), times, 120, 0, seeded
    )
    assert accepted == []
    assert rejected == []


def test_exhausted_starts_after_overlap_pruning_report_overlap() -> None:
    times = regular_times(24)
    valid = np.arange(24 - 12 + 1, dtype=np.int64)
    accepted, rejected = place_episodes(
        valid,
        times,
        120,
        3,
        lambda _k: AscendingGenerator(),
        min_gap_seconds=0.0,
    )
    assert accepted == [(0, 12), (12, 12)]
    # Starts 0..11 were pruned after the first placement; the third request
    # has nothing left, and the cause is overlap, not a missing start.
    assert rejected == [(2, "overlap")]


def test_placement_rejects_unsorted_times_and_bad_starts() -> None:
    times = np.array([0, 10, 5, 30], dtype=np.int64)
    with pytest.raises(ValueError, match="sorted"):
        place_episodes(np.array([0], dtype=np.int64), times, 20, 1, seeded)

    times = regular_times(30)
    with pytest.raises(ValueError, match="valid_starts"):
        place_episodes(np.array([25], dtype=np.int64), times, 120, 1, seeded)
