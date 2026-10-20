"""Read-only access to the fixed aircraft split.

The split file is a JSON object with exactly ``train``, ``val`` and ``test``
keys, each mapping to a list of zero-padded lowercase hex ``icao24`` strings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

SPLIT_NAMES: tuple[str, str, str] = ("train", "val", "test")


class SplitError(ValueError):
    """Raised when the split file is malformed, overlapping, or incomplete."""


@dataclass(frozen=True)
class SplitMap:
    """Immutable aircraft-to-split assignment."""

    assignments: Mapping[str, str]

    def split_of(self, icao24: str) -> str:
        """Return ``train``, ``val`` or ``test`` for an aircraft."""
        return self.assignments[icao24]

    @property
    def counts(self) -> dict[str, int]:
        counts = {name: 0 for name in SPLIT_NAMES}
        for name in self.assignments.values():
            counts[name] += 1
        return counts

    @property
    def aircraft(self) -> frozenset[str]:
        return frozenset(self.assignments)

    def by_split(self) -> dict[str, frozenset[str]]:
        grouped: dict[str, set[str]] = {name: set() for name in SPLIT_NAMES}
        for icao24, name in self.assignments.items():
            grouped[name].add(icao24)
        return {name: frozenset(values) for name, values in grouped.items()}


def load_split_aircraft(path: str | Path) -> SplitMap:
    """Load and structurally validate a fixed aircraft split file."""
    split_path = Path(path)
    with split_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise SplitError(f"{split_path} must contain a JSON object")

    missing = [name for name in SPLIT_NAMES if name not in data]
    if missing:
        raise SplitError("missing split name(s): " + ", ".join(missing))
    unexpected = [name for name in data if name not in SPLIT_NAMES]
    if unexpected:
        raise SplitError("unexpected split name(s): " + ", ".join(sorted(unexpected)))

    assignments: dict[str, str] = {}
    for name in SPLIT_NAMES:
        values = data[name]
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            raise SplitError(f"split {name!r} must be a list of strings")
        if len(values) != len(set(values)):
            raise SplitError(f"split {name!r} contains duplicate icao24 values")
        for icao24 in values:
            if icao24 in assignments:
                raise SplitError(
                    f"overlap: icao24 {icao24!r} appears in "
                    f"{assignments[icao24]!r} and {name!r}"
                )
            assignments[icao24] = name

    return SplitMap(MappingProxyType(assignments))


def validate_splits(
    splits: SplitMap,
    expected_icao24: Iterable[str] | None = None,
) -> None:
    """Verify disjointness (always) and exact coverage when expected IDs are given."""
    by_split = splits.by_split()
    names = list(by_split)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            overlap = by_split[left] & by_split[right]
            if overlap:
                raise SplitError(
                    f"overlap between {left!r} and {right!r}: "
                    f"{len(overlap)} aircraft"
                )

    if expected_icao24 is None:
        return

    expected = frozenset(expected_icao24)
    missing = expected - splits.aircraft
    extraneous = splits.aircraft - expected
    if missing:
        raise SplitError(
            f"missing {len(missing)} aircraft from the split; "
            f"examples: {sorted(missing)[:3]}"
        )
    if extraneous:
        raise SplitError(
            f"extraneous {len(extraneous)} aircraft not in the cleaned table; "
            f"examples: {sorted(extraneous)[:3]}"
        )
