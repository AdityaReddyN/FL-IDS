"""Ranked quota selection for Stage 1 overlays (two passes, deterministic).

Pass 1 computes eligibility and the overlay-keyed ``selection_u`` for every
segment without building any episode (see :func:`assembler.segment_selection`).
Then, per overlay and split ("cell"), the lowest-``u`` eligible segments are
taken until BOTH the target episode count and the target unique-aircraft count
are met. Pass 2 (the assembler, given the returned ``chosen`` set) builds
episodes only for the selected segments.

Selection is deterministic and chunk-order independent: ``selection_u`` depends
only on ``(global_seed, icao24, segment_id, overlay_key)`` and the ranking tie-
breaks on ``(selection_u, icao24, segment_id)``. The ranked rule reduces to the
Bernoulli rule when the quota is not binding: taking the lowest-``u`` segments
up to ``k`` selects exactly the segments with the ``k`` smallest ``u``, which is
the same set Bernoulli selects at the threshold that admits those ``k``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from .assembler import OverlaySpec, segment_selection
from .keys import add_natural_keys
from .splits import SPLIT_NAMES


class CapacityShortfallError(RuntimeError):
    """Raised when a quota cell cannot meet its episode/aircraft target."""

    def __init__(self, shortfall_table: list[dict]):
        self.shortfall_table = shortfall_table
        lines = [
            f"{row['overlay_key']} / {row['split']}: "
            f"episodes {row['realized_episodes']}/{row['requested_episodes']}, "
            f"aircraft {row['realized_unique_aircraft']}/{row['requested_unique_aircraft']}"
            for row in shortfall_table
        ]
        super().__init__("quota capacity shortfall:\n" + "\n".join(lines))


@dataclass(frozen=True)
class QuotaTarget:
    """Per-split episode and unique-aircraft targets for one overlay."""

    episodes: dict[str, int]
    unique_aircraft: dict[str, int]


def resolve_quota_target(config: Mapping, entry: Mapping) -> QuotaTarget:
    """Resolve a plan entry's ``quota_target`` against the config defaults.

    ``quota_target`` may give ``episodes`` / ``unique_aircraft`` as an int
    (applied to every split) or a per-split mapping. Anything omitted falls back
    to the config ``quota_mode`` per-cell targets.
    """
    quota_mode = config.get("quota_mode", {}) or {}
    default_episodes = quota_mode.get("target_episodes_per_cell", {})
    default_aircraft = quota_mode.get("target_unique_aircraft_per_cell", {})
    target = entry.get("quota_target")
    target = target if isinstance(target, Mapping) else {}

    def _per_split(value, default: Mapping) -> dict[str, int]:
        if value is None:
            return {split: int(default[split]) for split in SPLIT_NAMES if split in default}
        if isinstance(value, Mapping):
            return {split: int(value[split]) for split in SPLIT_NAMES if split in value}
        return {split: int(value) for split in SPLIT_NAMES}

    return QuotaTarget(
        episodes=_per_split(target.get("episodes"), default_episodes),
        unique_aircraft=_per_split(target.get("unique_aircraft"), default_aircraft),
    )


def overlay_capacity(
    df: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    *,
    grid_degrees: float = 5.0,
) -> dict[str, dict[str, int]]:
    """Per-split eligible segments, eligible starts, and unique aircraft.

    Pure pass-1 capacity scan (no episode building), used by the read-only
    capacity study to size how many overlays a merged dataset can host.
    """
    keyed = add_natural_keys(df).sort_values(
        ["icao24", "segment_id", "time"], kind="mergesort"
    ).reset_index(drop=True)
    stats = {split: {"eligible_segments": 0, "eligible_starts": 0, "_aircraft": set()} for split in SPLIT_NAMES}
    for (icao24, segment_id), seg in keyed.groupby(["icao24", "segment_id"], sort=True):
        seg = seg.reset_index(drop=True)
        sel = segment_selection(seg, icao24, segment_id, overlay, global_seed, split_of, grid_degrees)
        if sel.eligible:
            entry = stats[sel.split]
            entry["eligible_segments"] += 1
            entry["eligible_starts"] += int(sel.n_eligible_starts)
            entry["_aircraft"].add(str(icao24))
    return {
        split: {
            "eligible_segments": entry["eligible_segments"],
            "eligible_starts": entry["eligible_starts"],
            "unique_aircraft": len(entry["_aircraft"]),
        }
        for split, entry in stats.items()
    }


def select_quota_segments(
    df: pd.DataFrame,
    overlays: tuple[OverlaySpec, ...] | list[OverlaySpec],
    global_seed: int,
    split_of: Callable[[str], str],
    quota_targets: Mapping[str, QuotaTarget],
    *,
    grid_degrees: float = 5.0,
    fail_on_capacity_shortfall: bool = True,
) -> dict:
    """Return the chosen segments and a per-cell requested/feasible/realized report.

    ``chosen`` is a set of ``(icao24, segment_id, overlay_key)`` for pass 2.
    """
    keyed = add_natural_keys(df).sort_values(
        ["icao24", "segment_id", "time"], kind="mergesort"
    ).reset_index(drop=True)
    # Per (overlay_key, split): list of (selection_u, icao24, segment_id) for
    # eligible segments. Chunk order never changes this because u is per-segment.
    eligible_by_cell: dict[tuple[str, str], list[tuple[float, str, int]]] = {}
    for (icao24, segment_id), seg in keyed.groupby(["icao24", "segment_id"], sort=True):
        seg = seg.reset_index(drop=True)
        for overlay in overlays:
            sel = segment_selection(seg, icao24, segment_id, overlay, global_seed, split_of, grid_degrees)
            if sel.eligible:
                eligible_by_cell.setdefault((overlay.overlay_key, sel.split), []).append(
                    (sel.selection_u, str(icao24), int(segment_id))
                )

    chosen: set[tuple[str, int, str]] = set()
    report: list[dict] = []
    shortfall: list[dict] = []
    for overlay in overlays:
        target = quota_targets[overlay.overlay_key]
        episodes_per_segment = int(overlay.episodes_per_segment)
        for split in SPLIT_NAMES:
            candidates = sorted(eligible_by_cell.get((overlay.overlay_key, split), []))
            feasible_segments = len(candidates)
            feasible_aircraft = len({icao for _u, icao, _seg in candidates})
            want_episodes = int(target.episodes.get(split, 0))
            want_aircraft = int(target.unique_aircraft.get(split, 0))
            picked_aircraft: set[str] = set()
            picked_segments = 0
            for _u, icao, segment_id in candidates:
                episodes_estimate = picked_segments * episodes_per_segment
                if episodes_estimate >= want_episodes and len(picked_aircraft) >= want_aircraft:
                    break
                chosen.add((icao, segment_id, overlay.overlay_key))
                picked_aircraft.add(icao)
                picked_segments += 1
            realized_episodes = picked_segments * episodes_per_segment
            cell = {
                "overlay_key": overlay.overlay_key,
                "split": split,
                "requested_episodes": want_episodes,
                "requested_unique_aircraft": want_aircraft,
                "feasible_segments": feasible_segments,
                "feasible_unique_aircraft": feasible_aircraft,
                "realized_segments": picked_segments,
                "realized_episodes": realized_episodes,
                "realized_unique_aircraft": len(picked_aircraft),
                "episodes_per_segment": episodes_per_segment,
                "episodes_shortfall": realized_episodes < want_episodes,
                "aircraft_shortfall": len(picked_aircraft) < want_aircraft,
            }
            report.append(cell)
            if cell["episodes_shortfall"] or cell["aircraft_shortfall"]:
                shortfall.append(cell)

    if shortfall and fail_on_capacity_shortfall:
        raise CapacityShortfallError(shortfall)

    return {
        "chosen": chosen,
        "per_cell": report,
        "shortfall": shortfall,
        "fail_on_capacity_shortfall": bool(fail_on_capacity_shortfall),
    }
