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

from .assembler import OverlaySpec, _required, segment_selection
from .eligibility import pair_valid, row_eligible
from .episode import REPLAY_FAMILIES
from .keys import add_natural_keys
from .placement import MAX_SPAN_FACTOR, MIN_SPAN_FACTOR, rows_for_duration
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


def overlay_capacity_reference(
    df: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    *,
    grid_degrees: float = 5.0,
) -> dict[str, dict[str, int]]:
    """Per-split eligible segments/starts/aircraft via the per-segment loop.

    Authoritative but slow (~7 ms/segment). :func:`overlay_capacity` is the
    vectorized equivalent; ``test_overlay_capacity_matches_reference`` pins them
    to the same output across families.
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


_KEY_OFFSET = 4_000_000_000  # exceeds any epoch time so group keys never overlap


def _replay_has_source(times, gid, row_ok, delay_s, tolerance_s) -> np.ndarray:
    """Vectorized equivalent of ``replay_source_offsets(...) >= 0`` within each segment.

    Uses a gid*OFFSET+time key so one global nearest-neighbour search stays
    inside a segment (key distance == time distance when the match shares gid).
    """
    n = times.size
    key = gid * _KEY_OFFSET + times
    desired = key - int(delay_s)
    right = np.clip(np.searchsorted(key, desired, side="left"), 0, n - 1)
    left = np.clip(right - 1, 0, n - 1)
    rd = np.abs(key[right] - desired)
    ld = np.abs(key[left] - desired)
    picked = np.where(rd < ld, right, left)
    dist = np.minimum(rd, ld)
    idx = np.arange(n)
    return (dist <= tolerance_s) & (gid[picked] == gid) & (picked < idx) & row_ok[picked]


def overlay_capacity(
    df: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    *,
    grid_degrees: float = 5.0,
) -> dict[str, dict[str, int]]:
    """Per-split eligible segments, eligible starts, and unique aircraft (vectorized).

    Reproduces :func:`overlay_capacity_reference` exactly (segment-aware prefix
    sums for eligible-window starts, a within-segment replay link, the
    geoaltitude glitch and span filters), without the per-segment Python loop.
    """
    keyed = df.sort_values(["icao24", "segment_id", "time"], kind="mergesort").reset_index(drop=True)
    n = len(keyed)
    empty = {s: {"eligible_segments": 0, "eligible_starts": 0, "unique_aircraft": 0} for s in SPLIT_NAMES}
    if n == 0:
        return empty
    icao = keyed["icao24"].astype(str).to_numpy()
    seg = keyed["segment_id"].to_numpy()
    times = keyed["time"].to_numpy(np.int64)
    new_group = np.ones(n, dtype=bool)
    new_group[1:] = (icao[1:] != icao[:-1]) | (seg[1:] != seg[:-1])
    gid = (np.cumsum(new_group) - 1).astype(np.int64)

    row_ok = row_eligible(keyed, _required(overlay))
    if overlay.attack_family in REPLAY_FAMILIES:
        row_ok = row_ok & _replay_has_source(times, gid, row_ok, overlay.replay_delay_s, overlay.replay_tolerance_s)
    if overlay.altitude_variant == "baro_plus_geo" and overlay.geoaltitude_glitch_threshold_m is not None:
        geo = keyed["geoaltitude"].to_numpy(float)
        same = np.zeros(n, dtype=bool); same[1:] = ~new_group[1:]
        diff = np.zeros(n, dtype=float); diff[1:] = np.abs(np.diff(geo))
        row_ok = row_ok & ~(same & (diff > overlay.geoaltitude_glitch_threshold_m))
    pair_ok = pair_valid(keyed)

    n_rows = rows_for_duration(overlay.duration_seconds)
    kept = np.empty(0, dtype=np.int64)
    if n_rows <= n:
        row_prefix = np.concatenate(([0], np.cumsum(row_ok, dtype=np.int64)))
        pair_prefix = np.concatenate(([0], np.cumsum(pair_ok, dtype=np.int64)))
        i = np.arange(n - n_rows + 1)
        within = gid[i] == gid[i + n_rows - 1]
        rows_full = (row_prefix[i + n_rows] - row_prefix[i]) == n_rows
        pairs_full = (pair_prefix[i + n_rows] - pair_prefix[i + 1]) == (n_rows - 1)
        starts = i[within & rows_full & pairs_full]
        if starts.size:
            span = times[starts + n_rows - 1] - times[starts]
            lower = MIN_SPAN_FACTOR * float(overlay.duration_seconds)
            upper = MAX_SPAN_FACTOR * float(overlay.duration_seconds)
            kept = starts[(span >= lower) & (span <= upper)]

    seg_starts = np.flatnonzero(new_group)
    icao_by_gid = icao[seg_starts]
    split_map = {ic: split_of(ic) for ic in set(icao_by_gid.tolist())}
    result = {s: {"eligible_segments": 0, "eligible_starts": 0, "unique_aircraft": 0} for s in SPLIT_NAMES}
    if kept.size == 0:
        return result
    kept_gid = gid[kept]
    kept_split = np.array([split_map[icao_by_gid[g]] for g in kept_gid], dtype=object)
    for split in SPLIT_NAMES:
        sel = kept_split == split
        if not sel.any():
            continue
        gids = np.unique(kept_gid[sel])
        result[split]["eligible_starts"] = int(sel.sum())
        result[split]["eligible_segments"] = int(gids.size)
        result[split]["unique_aircraft"] = int(len({icao_by_gid[g] for g in gids}))
    return result


def select_quota_segments(
    df: pd.DataFrame,
    overlays: tuple[OverlaySpec, ...] | list[OverlaySpec],
    global_seed: int,
    split_of: Callable[[str], str],
    quota_targets: Mapping[str, QuotaTarget],
    *,
    grid_degrees: float = 5.0,
    fail_on_capacity_shortfall: bool = True,
    max_episodes_per_aircraft: int = 3,
) -> dict:
    """Return the chosen segments and a per-cell requested/feasible/realized report.

    ``chosen`` is a set of ``(icao24, segment_id, overlay_key)`` for pass 2. At
    most ``max_episodes_per_aircraft`` episodes per aircraft per cell are taken
    (D-046), so one busy aircraft cannot dominate a cell.
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
            per_aircraft: dict[str, int] = {}
            picked_segments = 0
            for _u, icao, segment_id in candidates:
                episodes_estimate = picked_segments * episodes_per_segment
                if episodes_estimate >= want_episodes and len(picked_aircraft) >= want_aircraft:
                    break
                if per_aircraft.get(icao, 0) * episodes_per_segment >= max_episodes_per_aircraft:
                    continue  # cap episodes per aircraft per cell (D-046)
                chosen.add((icao, segment_id, overlay.overlay_key))
                picked_aircraft.add(icao)
                per_aircraft[icao] = per_aircraft.get(icao, 0) + 1
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
