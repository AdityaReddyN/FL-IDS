"""Delayed data-layer replay for one episode (D-023).

Replay replaces a row's selected fields with a blend of the current value and
the value from a source row::

    modified = (1 - a_t) * current + a_t * source

Every source is read from the **original** arrays, never from values already
replayed in this call. Sources must be strictly earlier than their target
(``0 <= source_offsets[i] < i``); an active row with ``source_offsets == -1``
rejects the whole episode with ``reason="no_replay_source"`` rather than
edge-filling. Values of the listed fields at source rows must be finite on
active rows; violations raise ``ValueError``.

Heading blends along the shortest arc and is returned in ``[0, 360)``.
Longitude blends along the shortest arc and is wrapped into ``[-180, 180)``.
Fields not listed, and every row with ``a_t == 0``, are copied bit-identically.
The function is pure: inputs are copied and never mutated.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

ALLOWED_FIELDS: tuple[str, ...] = (
    "lat",
    "lon",
    "velocity",
    "heading",
    "vertrate",
    "baroaltitude",
    "geoaltitude",
)
PARTIAL_REPLAY_FIELDS: tuple[str, ...] = ("lat", "lon", "baroaltitude")
FULL_REPLAY_FIELDS: tuple[str, ...] = ALLOWED_FIELDS

NO_SOURCE_OFFSET = -1
ACTIVE_THRESHOLD = 0.0


@dataclass(frozen=True)
class ReplayResult:
    """Replayed arrays plus multipliers, achieved delays, and status.

    ``delays`` is ``times[i] - times[source_offsets[i]]`` in seconds, with
    ``NaN`` on inactive rows (and everywhere on a rejected episode).
    """

    values: dict[str, np.ndarray]
    multipliers: np.ndarray
    delays: np.ndarray
    rejected: bool = False
    reason: str | None = None


def _one_dimensional(values, name: str) -> np.ndarray:
    array = np.array(values, dtype=float, copy=True)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return array


def _multipliers(values, length: int) -> np.ndarray:
    array = _one_dimensional(values, "a")
    if array.shape != (length,):
        raise ValueError("a must have the same shape as the target arrays")
    if not np.all(np.isfinite(array)):
        raise ValueError("a must contain only finite values")
    if np.any(array < 0.0):
        raise ValueError("a must be non-negative")
    return array


def _source_offsets(values, length: int) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError("source_offsets must be one-dimensional")
    if array.shape != (length,):
        raise ValueError(
            "source_offsets must have the same shape as the target arrays"
        )
    if not np.issubdtype(array.dtype, np.integer):
        raise TypeError("source_offsets must contain integers")
    return array.astype(np.int64, copy=True)


def _times(values, length: int) -> np.ndarray:
    array = _one_dimensional(values, "times")
    if array.shape != (length,):
        raise ValueError("times must have the same shape as the target arrays")
    return array


def _shortest_arc_degrees(delta: np.ndarray) -> np.ndarray:
    """Wrap a degree difference into ``[-180, 180)``."""
    return (delta + 180.0) % 360.0 - 180.0


def _wrap_longitude(values: np.ndarray) -> np.ndarray:
    """Wrap into ``[-180, 180)``, mapping the rounded ``+180`` end to ``-180``."""
    wrapped = (values + 180.0) % 360.0 - 180.0
    return np.where(wrapped >= 180.0, -180.0, wrapped)


def _blend_longitude(current, source, multipliers) -> np.ndarray:
    blended = current + multipliers * _shortest_arc_degrees(source - current)
    return _wrap_longitude(blended)


def _blend_heading(current, source, multipliers) -> np.ndarray:
    blended = current + multipliers * _shortest_arc_degrees(source - current)
    wrapped = np.mod(blended, 360.0)
    return np.where(wrapped >= 360.0, 0.0, wrapped)


def _reject(
    originals: dict[str, np.ndarray],
    multipliers: np.ndarray,
    reason: str,
) -> ReplayResult:
    return ReplayResult(
        values={name: array.copy() for name, array in originals.items()},
        multipliers=multipliers,
        delays=np.full(multipliers.size, np.nan),
        rejected=True,
        reason=reason,
    )


def replay_fields(
    values: Mapping[str, np.ndarray],
    source_offsets,
    a,
    fields,
    times,
) -> ReplayResult:
    """Replay ``fields`` using original values at ``source_offsets``.

    ``values`` must contain every listed field (and may contain the other
    allowed fields). ``source_offsets`` and ``times`` are per-row arrays; the
    source row for an active row ``i`` must satisfy
    ``0 <= source_offsets[i] < i``. See the module docstring for blending and
    rejection rules.
    """
    if not isinstance(values, Mapping):
        raise TypeError("values must be a mapping of field name to array")

    field_names = tuple(dict.fromkeys(fields))
    unknown = [name for name in field_names if name not in ALLOWED_FIELDS]
    if unknown:
        raise ValueError(
            "fields must be a subset of the allowed replay fields "
            f"{ALLOWED_FIELDS}; got {unknown}"
        )
    missing = [name for name in field_names if name not in values]
    if missing:
        raise KeyError(
            "values is missing replay field(s): " + ", ".join(missing)
        )

    if not values:
        raise ValueError("values must contain at least one field")

    originals: dict[str, np.ndarray] = {}
    length = None
    for name, array in values.items():
        converted = _one_dimensional(array, name)
        if length is None:
            length = converted.size
        elif converted.size != length:
            raise ValueError("all value arrays must have the same length")
        originals[name] = converted

    multipliers = _multipliers(a, length)
    sources = _source_offsets(source_offsets, length)
    time_values = _times(times, length)

    active = multipliers > ACTIVE_THRESHOLD
    no_source = active & (sources == NO_SOURCE_OFFSET)
    if np.any(no_source):
        return _reject(originals, multipliers, "no_replay_source")

    rows = np.arange(length)
    invalid = active & ((sources < 0) | (sources >= rows))
    if np.any(invalid):
        raise ValueError(
            "active rows require 0 <= source_offsets[i] < i; "
            f"invalid row(s): {np.flatnonzero(invalid).tolist()}"
        )

    active_sources = sources[active]
    for name in field_names:
        source_values = originals[name][active_sources]
        if np.any(~np.isfinite(source_values)):
            raise ValueError(
                f"{name} has NaN or inf at a replay source row"
            )

    delays = np.full(length, np.nan)
    delays[active] = time_values[active] - time_values[active_sources]

    output = {name: array.copy() for name, array in originals.items()}
    if np.any(active):
        current_multipliers = multipliers[active]
        for name in field_names:
            current = originals[name]
            source = originals[name][active_sources]
            if name == "lon":
                blended = _blend_longitude(
                    current[active], source, current_multipliers
                )
            elif name == "heading":
                blended = _blend_heading(
                    current[active], source, current_multipliers
                )
            else:
                blended = (
                    (1.0 - current_multipliers) * current[active]
                    + current_multipliers * source
                )
            output[name][active] = blended

    return ReplayResult(
        values=output, multipliers=multipliers, delays=delays
    )
