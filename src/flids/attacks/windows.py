"""Window labelling for one aircraft segment (D-024).

Windows follow ``scripts/build_sequences_v2.py``: a segment is cut into
``window_rows``-row windows with a fixed stride, starting at row 0, and only
full windows are emitted (``range(0, len - window_rows + 1, stride)``).
Window offsets are segment-relative, so they line up with the attacks'
``start_offset`` convention.

Labels use the decoupled truth/detectability rule of D-019/D-020::

    normal    : no row has a_t > 0
    attacked  : at least MIN_EFFECTIVE_ROWS rows have a_t >= 0.5
    ambiguous : attacked rows exist but fewer than MIN_EFFECTIVE_ROWS are
                effective

For gradual episodes the multipliers passed here must be the **realized**
multipliers ``a_t * g_t`` (D-023). Strata describe where the window sits
relative to the episode boundaries: ``boundary`` if the window contains an
onset or offset row, ``interior_only`` if it contains attack rows but no
boundary row, and ``none`` if it contains no attack row. Residual strata are
not computed here.
"""

from __future__ import annotations

import numpy as np

from .ramps import EFFECTIVE_THRESHOLD, attack_row_mask, effective_row_mask

DEFAULT_WINDOW_ROWS = 30
DEFAULT_STRIDE = 10
WINDOW_ROWS = DEFAULT_WINDOW_ROWS
WINDOW_STRIDE = DEFAULT_STRIDE
MIN_EFFECTIVE_ROWS = 5

WINDOW_LABELS: tuple[str, ...] = ("normal", "attacked", "ambiguous")
WINDOW_STRATA: tuple[str, ...] = ("none", "boundary", "interior_only")
BOUNDARY_POSITIONS = ("onset", "offset")


def _one_dimensional(values, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def _positive_int(value, name: str) -> int:
    if not isinstance(value, (int, np.integer)) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return int(value)


def label_windows(
    multipliers_full,
    positions_full,
    episode_ids_full,
    window_rows: int = DEFAULT_WINDOW_ROWS,
    stride: int = DEFAULT_STRIDE,
) -> list[dict]:
    """Return one label record per full window of a single segment.

    ``multipliers_full`` holds the realized per-row multipliers and
    ``positions_full`` the episode positions (``"onset"``, ``"interior"``,
    ``"offset"``, or ``"none"`` outside episodes). ``episode_ids_full`` holds
    ``-1`` outside episodes. A window that overlaps two different episodes is
    a placement error and raises ``AssertionError``.
    """
    multipliers = np.asarray(multipliers_full, dtype=float)
    if multipliers.ndim != 1:
        raise ValueError("multipliers must be one-dimensional")
    if not np.all(np.isfinite(multipliers)):
        raise ValueError("multipliers must contain only finite values")
    if np.any(multipliers < 0.0):
        raise ValueError("multipliers must be non-negative")

    positions = _one_dimensional(positions_full, "positions")
    episode_ids = _one_dimensional(episode_ids_full, "episode_ids")
    if positions.shape != multipliers.shape:
        raise ValueError(
            "positions and multipliers must have equal length"
        )
    if episode_ids.shape != multipliers.shape:
        raise ValueError(
            "episode_ids and multipliers must have equal length"
        )
    window_rows = _positive_int(window_rows, "window_rows")
    stride = _positive_int(stride, "stride")

    attack = attack_row_mask(multipliers)
    effective = effective_row_mask(multipliers)
    windows: list[dict] = []
    start_offsets = range(
        0, multipliers.size - window_rows + 1, stride
    )
    for window_id, start in enumerate(start_offsets):
        stop = start + window_rows
        attack_window = attack[start:stop]
        n_attack_rows = int(np.count_nonzero(attack_window))
        n_effective_rows = int(
            np.count_nonzero(effective[start:stop])
        )

        if n_attack_rows == 0:
            label = "normal"
            stratum = "none"
            episode_id = -1
        else:
            active_ids = set(
                int(value)
                for value in episode_ids[start:stop][attack_window]
            )
            assert len(active_ids) == 1, (
                "a window overlaps more than one episode: "
                f"episode ids {sorted(active_ids)} in rows "
                f"[{start}, {stop})"
            )
            episode_id = active_ids.pop()
            assert episode_id >= 0, (
                "attack rows must carry a non-negative episode id"
            )
            label = (
                "attacked"
                if n_effective_rows >= MIN_EFFECTIVE_ROWS
                else "ambiguous"
            )
            window_positions = positions[start:stop][attack_window]
            boundary = any(
                position in BOUNDARY_POSITIONS
                for position in window_positions
            )
            stratum = "boundary" if boundary else "interior_only"

        windows.append(
            {
                "window_id": window_id,
                "start_offset": start,
                "n_rows": window_rows,
                "label": label,
                "stratum": stratum,
                "n_attack_rows": n_attack_rows,
                "n_effective_rows": n_effective_rows,
                "episode_id": episode_id,
            }
        )
    return windows
