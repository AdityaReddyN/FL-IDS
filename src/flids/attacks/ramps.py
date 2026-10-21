"""Ramp multipliers for episode onset and offset (D-022).

Conventions
-----------
* ``linear_mix``: onset row ``k`` (0-based) has ``a_k = (k + 1) / (ramp_rows + 1)``,
  so a 3-row ramp gives 0.25, 0.50, 0.75; interior rows are 1.0; the offset is
  the mirror image (0.75, 0.50, 0.25 before the last row). The episode must
  have at least ``2 * ramp_rows + 1`` rows.
* ``abrupt``: every row is 1.0; the first row is ``"onset"``, the last row is
  ``"offset"`` (a single-row episode is ``"onset"``), and the rest are
  ``"interior"``.

A row is an **attack row** when ``a_t > 0`` and an **effective row** when
``a_t >= 0.5``. These thresholds are implementation choices recorded in D-022;
window labelling itself is out of scope for this module.
"""

from __future__ import annotations

import numpy as np

ATTACK_THRESHOLD = 0.0
EFFECTIVE_THRESHOLD = 0.5

POSITION_ONSET = "onset"
POSITION_INTERIOR = "interior"
POSITION_OFFSET = "offset"

POSITION_NAMES = (POSITION_ONSET, POSITION_INTERIOR, POSITION_OFFSET)
MODES = ("linear_mix", "abrupt")


def _positive_int(value, name: str) -> int:
    if not isinstance(value, (int, np.integer)) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return int(value)


def ramp_multipliers(
    n_rows,
    ramp_rows: int = 3,
    mode: str = "linear_mix",
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(multipliers, positions)`` for one episode.

    ``multipliers`` is a float64 array of per-row ``a_t``; ``positions`` is a
    string array with ``"onset"``, ``"interior"``, or ``"offset"`` per row.
    ``linear_mix`` raises ``ValueError`` when
    ``n_rows < 2 * ramp_rows + 1``.
    """
    n_rows = _positive_int(n_rows, "n_rows")
    ramp_rows = _positive_int(ramp_rows, "ramp_rows")
    if mode not in MODES:
        raise ValueError(
            f"mode must be one of {MODES!r}; got {mode!r}"
        )

    positions = np.full(n_rows, POSITION_INTERIOR, dtype="<U8")
    if mode == "abrupt":
        multipliers = np.ones(n_rows, dtype=np.float64)
        positions[0] = POSITION_ONSET
        if n_rows > 1:
            positions[-1] = POSITION_OFFSET
        return multipliers, positions

    minimum = 2 * ramp_rows + 1
    if n_rows < minimum:
        raise ValueError(
            f"linear_mix requires n_rows >= 2*ramp_rows+1; "
            f"n_rows must be at least {minimum}, got {n_rows}"
        )

    multipliers = np.ones(n_rows, dtype=np.float64)
    multipliers[:ramp_rows] = (
        np.arange(1, ramp_rows + 1, dtype=np.float64) / (ramp_rows + 1)
    )
    multipliers[-ramp_rows:] = (
        np.arange(ramp_rows, 0, -1, dtype=np.float64) / (ramp_rows + 1)
    )
    positions[:ramp_rows] = POSITION_ONSET
    positions[-ramp_rows:] = POSITION_OFFSET
    return multipliers, positions


def _multiplier_array(multipliers) -> np.ndarray:
    values = np.asarray(multipliers, dtype=float)
    if values.ndim != 1:
        raise ValueError("multipliers must be one-dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("multipliers must contain only finite values")
    return values


def attack_row_mask(multipliers) -> np.ndarray:
    """Return ``a_t > 0`` for each row."""
    return _multiplier_array(multipliers) > ATTACK_THRESHOLD


def effective_row_mask(multipliers) -> np.ndarray:
    """Return ``a_t >= 0.5`` for each row."""
    return _multiplier_array(multipliers) >= EFFECTIVE_THRESHOLD


def effective_row_count(multipliers) -> int:
    """Return the number of effective rows (``a_t >= 0.5``).

    For gradual deviation the caller must pass the *realized* multipliers
    ``a_t * g_t``, not the ramp multipliers alone (D-023). Gradual episodes
    need at least five effective rows before the assembler will accept them;
    that rejection belongs to Session 3c and is not implemented here.
    """
    return int(np.count_nonzero(effective_row_mask(multipliers)))
