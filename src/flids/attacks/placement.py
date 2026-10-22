"""Deterministic episode placement inside one aircraft segment.

A request is placed in three steps: filter eligible window starts by their
actual time span, shuffle the remaining starts with the request's own
generator, and take the first start that neither overlaps an accepted episode
nor violates the minimum inter-episode gap.

The span factors are provisional implementation choices (D-021): a window of
``n_rows = duration_seconds // 10`` rows spans ``n_rows - 1`` sampling
intervals, so its actual span is normally a little below the requested
duration. Irregular sampling can stretch it further.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

ROWS_PER_SECOND = 0.1
MIN_SPAN_FACTOR = 0.8
MAX_SPAN_FACTOR = 1.25

REJECTION_REASONS = (
    "segment_too_short",
    "no_eligible_start",
    "overlap",
    "gap_violation",
    "max_per_segment_exceeded",
)


def rows_for_duration(duration_seconds: float) -> int:
    """Return ``duration_seconds // 10`` as an integer row count."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    return int(duration_seconds) // 10


def filter_starts_by_span(
    valid_starts,
    segment_times,
    n_rows: int,
    duration_seconds: float,
) -> tuple[np.ndarray, int]:
    """Keep starts whose actual window span is within the provisional factors.

    Returns ``(kept_starts, removed_count)``. The caller can use
    ``removed_count`` for reporting; placement applies the same filter
    internally.
    """
    if n_rows < 1:
        raise ValueError("n_rows must be positive")
    times = np.asarray(segment_times, dtype=np.int64)
    if times.ndim != 1:
        raise ValueError("segment_times must be one-dimensional")

    starts = np.asarray(valid_starts, dtype=np.int64)
    if starts.ndim != 1:
        raise ValueError("valid_starts must be one-dimensional")
    if starts.size and (
        starts.min() < 0 or starts.max() > len(times) - n_rows
    ):
        raise ValueError("valid_starts contains an out-of-range start")

    if starts.size == 0:
        return starts, 0

    span = times[starts + n_rows - 1] - times[starts]
    lower = MIN_SPAN_FACTOR * float(duration_seconds)
    upper = MAX_SPAN_FACTOR * float(duration_seconds)
    keep = (span >= lower) & (span <= upper)
    kept = np.unique(starts[keep])
    removed = int(starts.size - kept.size)
    return kept, removed


def _overlaps(start: int, accepted, n_rows: int) -> bool:
    for accepted_start, _ in accepted:
        if start < accepted_start + n_rows and accepted_start < start + n_rows:
            return True
    return False


def _gap_ok(
    start: int,
    accepted,
    times: np.ndarray,
    n_rows: int,
    min_gap_seconds: float,
) -> bool:
    candidate_start = times[start]
    candidate_end = times[start + n_rows - 1]
    for accepted_start, _ in accepted:
        accepted_start_time = times[accepted_start]
        accepted_end_time = times[accepted_start + n_rows - 1]
        gap = max(candidate_start, accepted_start_time) - min(
            candidate_end, accepted_end_time
        )
        if gap < min_gap_seconds:
            return False
    return True


def place_episodes(
    valid_starts,
    segment_times,
    duration_seconds: float,
    n_requested: int,
    rng_for_request: Callable[[int], np.random.Generator],
    max_per_segment: int = 3,
    min_gap_seconds: float = 600.0,
) -> tuple[list[tuple[int, int]], list[tuple[int, str]]]:
    """Place up to ``n_requested`` episodes in one segment.

    Returns ``(accepted, rejected)``:

    * ``accepted`` is ``(request_index, start_offset, n_rows)`` in request order.
    * ``rejected`` is ``(request_index, reason)`` where reason is one of
      :data:`REJECTION_REASONS`.

    Request ``k`` uses ``rng_for_request(k)``; the draw for one request never
    depends on other requests, so appending later requests cannot change
    earlier placements. Gap failures do not consume a candidate: a start that
    fails the gap for this request can still be used by a later one.
    """
    times = np.asarray(segment_times, dtype=np.int64)
    if times.ndim != 1:
        raise ValueError("segment_times must be one-dimensional")
    if np.any(np.diff(times) <= 0):
        raise ValueError("segment_times must be strictly increasing (sorted)")

    if not isinstance(n_requested, (int, np.integer)) or isinstance(
        n_requested, bool
    ):
        raise TypeError("n_requested must be an integer")
    if n_requested < 0:
        raise ValueError("n_requested must be non-negative")
    if not isinstance(max_per_segment, (int, np.integer)) or isinstance(
        max_per_segment, bool
    ):
        raise TypeError("max_per_segment must be an integer")
    if max_per_segment < 0:
        raise ValueError("max_per_segment must be non-negative")
    if min_gap_seconds < 0:
        raise ValueError("min_gap_seconds must be non-negative")
    if not callable(rng_for_request):
        raise TypeError("rng_for_request must be callable")

    n_rows = rows_for_duration(duration_seconds)
    if n_rows < 1:
        raise ValueError("duration_seconds must be at least 10")

    if n_rows > len(times):
        rejected = [(k, "segment_too_short") for k in range(n_requested)]
        return [], rejected

    available, _ = filter_starts_by_span(
        valid_starts, times, n_rows, duration_seconds
    )
    if n_requested == 0 or available.size == 0 or max_per_segment == 0:
        reason = (
            "no_eligible_start"
            if available.size == 0
            else "max_per_segment_exceeded"
        )
        return [], [(k, reason) for k in range(n_requested)]

    accepted: list[tuple[int, int, int]] = []
    rejected: list[tuple[int, str]] = []
    overlap_pruned = 0

    for request_index in range(n_requested):
        if len(accepted) >= max_per_segment:
            rejected.append((request_index, "max_per_segment_exceeded"))
            continue

        order = np.asarray(
            rng_for_request(request_index).permutation(available),
            dtype=np.int64,
        )
        chosen = None
        saw_overlap = False
        saw_gap = False
        for raw_start in order:
            start = int(raw_start)
            placed = [(item[1], item[2]) for item in accepted]
            if _overlaps(start, placed, n_rows):
                saw_overlap = True
                continue
            if not _gap_ok(
                start, placed, times, n_rows, min_gap_seconds
            ):
                saw_gap = True
                continue
            chosen = start
            break

        if chosen is None:
            if saw_gap:
                reason = "gap_violation"
            elif saw_overlap or overlap_pruned > 0:
                # Starts pruned after earlier placements are no longer in
                # ``available``; remember that they were removed by overlap.
                reason = "overlap"
            else:
                reason = "no_eligible_start"
            rejected.append((request_index, reason))
            continue

        accepted.append((request_index, chosen, n_rows))
        before = available.size
        available = available[
            (available + n_rows <= chosen) | (available >= chosen + n_rows)
        ]
        overlap_pruned += int(before - available.size)

    return accepted, rejected
