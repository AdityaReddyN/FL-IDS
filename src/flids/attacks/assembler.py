"""Pure, in-memory assembly of one row-level Stage 1 overlay (D-025)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .eligibility import REQUIRED_FIELDS, eligible_starts, pair_valid, replay_source_offsets, row_eligible
from .episode import EpisodeSpec, HORIZONTAL_FAMILIES, MIN_EFFECTIVE_ROWS, REPLAY_FAMILIES, build_episode
from .kinematics import speed_band
from .ramps import effective_row_count, ramp_multipliers
from .keys import add_natural_keys
from .placement import filter_starts_by_span, place_episodes, rows_for_duration
from .seeding import episode_rng, overlay_selection_rng, parameter_rng, placement_rng
from .schemas import FEATURE_FIELDS, TABLE_NAMES, empty_table, validate_table
from .windows import label_windows


@dataclass(frozen=True)
class OverlaySpec:
    attack_family: str
    tier: str
    subtype: str | None = None
    altitude_variant: str | None = None
    onset_mode: str = "linear_mix"
    duration_seconds: float = 120.0
    ramp_rows: int = 3
    magnitude_m: float | None = None
    sigma_m: float | None = None
    kappa: float = 0.0
    per_step_sigma_m: float = 25.0
    shift_m: float | None = None
    replay_delay_s: float = 300.0
    replay_tolerance_s: float = 5.0
    tau: float = 0.1
    episodes_per_segment: int = 1
    dataset_mode: str = "uniform_per_subairspace"
    overlay_key: str | None = None
    geoaltitude_glitch_threshold_m: float | None = None
    min_gap_seconds: float = 600.0

    def __post_init__(self):
        if not 0 <= self.tau <= 1: raise ValueError("tau must be in [0, 1]")
        if not 1 <= self.episodes_per_segment <= 3: raise ValueError("episodes_per_segment must be in 1..3")
        if self.dataset_mode != "uniform_per_subairspace": raise ValueError("unsupported dataset_mode")
        if self.overlay_key is None:
            parts = (self.attack_family, self.tier, self.subtype or "", self.altitude_variant or "")
            object.__setattr__(self, "overlay_key", "|".join(parts))
        elif not self.overlay_key:
            raise ValueError("overlay_key must be a non-empty string")
        _validate_effective_capacity(self)


def _realized_multipliers(overlay: "OverlaySpec", n_rows: int) -> np.ndarray:
    """Realized per-row multipliers for the overlay's onset and family.

    Mirrors :func:`episode.build_episode`: gradual deviation scales the ramp by
    a linear growth ``g_t`` (``a_t * g_t``); every other family uses the ramp
    multipliers directly. Used only to validate effective-row capacity.
    """
    multipliers, _positions = ramp_multipliers(n_rows, overlay.ramp_rows, overlay.onset_mode)
    if overlay.attack_family == "gradual_deviation":
        fractions = np.ones(1, dtype=float) if n_rows == 1 else np.arange(n_rows, dtype=float) / (n_rows - 1)
        return multipliers * fractions
    return multipliers


def _validate_effective_capacity(overlay: "OverlaySpec") -> None:
    """Reject an overlay whose realized multipliers yield < 5 effective rows.

    This catches configurations such as gradual deviation at 120 s, whose linear
    growth leaves too few rows at ``a_t >= 0.5`` to form a measurable episode
    (D-023). A too-short onset that :func:`ramp_multipliers` itself rejects is
    reported the same way.
    """
    n_rows = rows_for_duration(overlay.duration_seconds)
    try:
        realized = _realized_multipliers(overlay, n_rows)
    except ValueError as error:
        raise ValueError(
            f"overlay {overlay.overlay_key!r} cannot form an onset at "
            f"duration {overlay.duration_seconds} s ({n_rows} rows): {error}"
        ) from error
    effective = effective_row_count(realized)
    if effective < MIN_EFFECTIVE_ROWS:
        raise ValueError(
            f"overlay {overlay.overlay_key!r} yields only {effective} effective "
            f"row(s) at duration {overlay.duration_seconds} s ({n_rows} rows); "
            f"at least {MIN_EFFECTIVE_ROWS} are required"
        )


@dataclass(frozen=True)
class AssembledTables:
    attacked_rows: pd.DataFrame; step_labels: pd.DataFrame; episodes: pd.DataFrame
    rejected_candidates: pd.DataFrame; modified_row_provenance: pd.DataFrame
    windows: pd.DataFrame; segments: pd.DataFrame; overlay_selections: pd.DataFrame


def _cell(lat, lon, degrees):
    if not np.isfinite(lat) or not np.isfinite(lon): return "unknown"
    return f"{int(np.floor((lat + 90.) / degrees))}:{int(np.floor((lon + 180.) / degrees))}"


def _finite_median(values) -> float:
    """Return a finite-only median, or NaN when a coordinate is unavailable.

    Longitude uses the existing arithmetic-median convention; it is not
    antimeridian-aware and must not be interpreted as a circular median.
    """
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(np.median(finite)) if finite.size else float("nan")


def _episode_speed_band(seg, start, count) -> str:
    """Speed band of the median velocity over the episode rows.

    Returns ``"unknown"`` only when every episode-row velocity is missing.
    """
    velocity = seg.velocity.to_numpy(dtype=float)[start:start + count]
    finite = velocity[np.isfinite(velocity)]
    if not finite.size:
        return "unknown"
    return speed_band(float(np.median(finite)))


def _episode_id(icao24, segment_id, index, overlay_key):
    value = int.from_bytes(hashlib.sha256(f"{overlay_key}|{icao24}|{segment_id}|{index}".encode()).digest()[:8], "big")
    return value & ((1 << 63) - 1)


def _table(name, records):
    schema = empty_table(name)
    if not records: return schema
    out = pd.DataFrame(records)
    for column in schema:
        out[column] = out[column].astype(schema[column].dtype)
    return out[list(schema)]


def _table_from_columns(name, columns):
    """Build a typed output table from column arrays, avoiding row records."""
    schema = empty_table(name)
    out = pd.DataFrame(columns)
    for column in schema:
        out[column] = out[column].astype(schema[column].dtype)
    return out[list(schema)]


def _nullable_episode_ids(values):
    """Return exact nullable int64 IDs without lossy float64 coercion."""
    result = pd.array(values, dtype="Int64")
    result[np.asarray(values) < 0] = pd.NA
    return result


def _nullable_source_ids(values):
    result = pd.array(values, dtype="Int64")
    result[np.asarray(values) < 0] = pd.NA
    return result


def strict_json(value) -> str:
    """Encode JSON without non-standard NaN or Infinity tokens."""
    def clean(item):
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(val) for val in item]
        if isinstance(item, (float, np.floating)) and not np.isfinite(item):
            return None
        return item
    return json.dumps(clean(value), allow_nan=False, sort_keys=True, separators=(",", ":"))


def _required(overlay):
    if overlay.attack_family in HORIZONTAL_FAMILIES: return REQUIRED_FIELDS["horizontal_manipulation"]
    if overlay.attack_family == "freeze_fixed_value": return REQUIRED_FIELDS["freeze"]
    if overlay.attack_family == "altitude_constant_deviation":
        return REQUIRED_FIELDS["altitude_manipulation_baro_plus_geo"] if overlay.altitude_variant == "baro_plus_geo" else REQUIRED_FIELDS["altitude_manipulation"]
    return REQUIRED_FIELDS[overlay.attack_family]


@dataclass(frozen=True)
class SegmentSelection:
    """Eligibility and selection draw for one (overlay, segment); no episodes.

    This is the cheap pass-1 output: it computes everything needed to decide
    whether and how a segment is selected (Bernoulli or ranked quota) without
    building any episode. ``row_ok``, ``sources`` and ``starts`` are retained so
    the assembler's pass-2 reuses the exact same eligibility, never recomputing
    it differently.
    """
    icao24: str
    segment_id: int
    split: str
    cell_id: str
    n_eligible_starts: int
    eligible: bool
    selection_u: float
    row_ok: np.ndarray
    sources: np.ndarray | None
    starts: np.ndarray


def segment_selection(
    seg: pd.DataFrame,
    icao24: str,
    segment_id,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    grid_degrees: float,
) -> SegmentSelection:
    """Compute eligibility and the overlay-keyed ``selection_u`` for one segment.

    Deterministic and chunk-order independent: ``selection_u`` depends only on
    ``(global_seed, icao24, segment_id, overlay_key)``.
    """
    n_rows = rows_for_duration(overlay.duration_seconds)
    times = seg.time.to_numpy(np.int64)
    row_ok = row_eligible(seg, _required(overlay))
    sources = None
    if overlay.attack_family in REPLAY_FAMILIES:
        sources = replay_source_offsets(times, row_ok, overlay.replay_delay_s, overlay.replay_tolerance_s)
        row_ok = row_ok & (sources >= 0)
    if overlay.altitude_variant == "baro_plus_geo" and overlay.geoaltitude_glitch_threshold_m is not None:
        glitch = np.zeros(len(seg), dtype=bool)
        glitch[1:] = np.abs(np.diff(seg.geoaltitude.to_numpy(float))) > overlay.geoaltitude_glitch_threshold_m
        row_ok = row_ok & ~glitch
    starts = eligible_starts(seg, n_rows, row_ok, pair_valid(seg))
    starts, _ = filter_starts_by_span(starts, times, n_rows, overlay.duration_seconds)
    eligible = bool(len(starts))
    u = float(overlay_selection_rng(global_seed, icao24, segment_id, overlay.overlay_key).random())
    cell_id = _cell(_finite_median(seg.lat), _finite_median(seg.lon), grid_degrees)
    return SegmentSelection(
        icao24=str(icao24), segment_id=int(segment_id), split=split_of(icao24),
        cell_id=cell_id, n_eligible_starts=len(starts), eligible=eligible,
        selection_u=u, row_ok=row_ok, sources=sources, starts=starts,
    )


def _assemble_keyed(
    keyed: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    grid_degrees: float,
    chosen_segments: set | None = None,
) -> AssembledTables:
    """Assemble already-keyed rows; row/step tables are built column-wise.

    When ``chosen_segments`` is given (ranked quota mode), a segment is selected
    iff ``(icao24, segment_id, overlay_key)`` is in that set; otherwise selection
    is the Bernoulli rule ``eligible and selection_u < tau``.
    """
    attacked=[]; labels=[]; episodes=[]; rejected=[]; provenance=[]; windows=[]; segments=[]; overlay_selections=[]
    n_rows = rows_for_duration(overlay.duration_seconds)
    method = "ranked_quota_lowest_u_eligible_segment" if chosen_segments is not None else "bernoulli_overlay_keyed_eligible_segment"
    for (icao24, segment_id), seg in keyed.groupby(["icao24", "segment_id"], sort=True):
        seg = seg.reset_index(drop=True)
        times = seg.time.to_numpy(np.int64)
        source_ids = seg.source_row_id.to_numpy(np.int64)
        offsets = seg.segment_row_offset.to_numpy(np.int32)
        sel = segment_selection(seg, icao24, segment_id, overlay, global_seed, split_of, grid_degrees)
        split = sel.split
        row_ok = sel.row_ok
        sources = sel.sources
        starts = sel.starts
        eligible = sel.eligible
        u = sel.selection_u
        if chosen_segments is None:
            selected = eligible and u < overlay.tau
        else:
            selected = (str(icao24), int(segment_id), overlay.overlay_key) in chosen_segments
        segments.append(dict(icao24=icao24, segment_id=segment_id, split=split, n_rows=len(seg), cell_id=sel.cell_id, n_eligible_starts=len(starts), eligible=eligible, selection_u=u, selected=selected))
        overlay_selections.append(dict(icao24=icao24,segment_id=segment_id,split=split,overlay_key=overlay.overlay_key,attack_family=overlay.attack_family,tier=overlay.tier,n_eligible_starts=len(starts),eligible=eligible,selection_u=u,tau_requested=overlay.tau,selected=selected,chosen=selected))

        multipliers = np.zeros(len(seg), dtype=np.float64)
        positions = np.full(len(seg), "none", dtype=object)
        episode_ids = np.full(len(seg), -1, dtype=np.int64)
        modified = {field: seg[field].to_numpy(dtype=float, copy=True) for field in FEATURE_FIELDS}
        replay_source_ids = np.full(len(seg), -1, dtype=np.int64)
        replay_delays = np.full(len(seg), np.nan, dtype=np.float64)
        episode_family = np.full(len(seg), None, dtype=object)
        episode_subtype = np.full(len(seg), None, dtype=object)
        episode_tier = np.full(len(seg), None, dtype=object)
        meta = {}

        if selected:
            accepted, failures = place_episodes(starts, times, overlay.duration_seconds, overlay.episodes_per_segment, lambda k: placement_rng(global_seed, icao24, segment_id, k), max_per_segment=3, min_gap_seconds=overlay.min_gap_seconds)
            for k, reason in failures:
                rejected.append(dict(candidate_id=_episode_id(icao24,segment_id,k,overlay.overlay_key),overlay_key=overlay.overlay_key,icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,requested_start_row_offset=-1,requested_n_rows=n_rows,stage="placement",reason=reason,details_json="{}"))
            for k,start,count in accepted:
                prng=parameter_rng(global_seed,icao24,segment_id,k)
                bearing=float(prng.uniform(0,360)) if overlay.attack_family in HORIZONTAL_FAMILIES else None
                shift=(1 if prng.integers(2) else -1)*(overlay.shift_m or 0) if overlay.attack_family=="altitude_constant_deviation" else overlay.shift_m
                spec=EpisodeSpec(overlay.attack_family,overlay.tier,overlay.subtype,overlay.altitude_variant,overlay.onset_mode,overlay.ramp_rows,overlay.magnitude_m,bearing,overlay.sigma_m,overlay.kappa,overlay.per_step_sigma_m,shift,overlay.replay_delay_s,overlay.replay_tolerance_s)
                result=build_episode({f:seg[f].to_numpy(float) for f in FEATURE_FIELDS},times,row_ok,sources,start,count,spec,episode_rng(global_seed,icao24,segment_id,k))
                eid=_episode_id(icao24,segment_id,k,overlay.overlay_key)
                if not result.accepted:
                    rejected.append(dict(candidate_id=eid,overlay_key=overlay.overlay_key,icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,requested_start_row_offset=start,requested_n_rows=count,stage="build",reason=result.reason,details_json=json.dumps(result.summary,sort_keys=True)))
                    continue
                sl=slice(start,start+count)
                multipliers[sl]=result.multipliers
                positions[sl]=result.positions
                episode_ids[sl]=eid
                episode_family[sl]=overlay.attack_family
                episode_subtype[sl]=overlay.subtype or overlay.attack_family
                episode_tier[sl]=overlay.tier
                meta[eid]=(overlay.attack_family,overlay.subtype or overlay.attack_family,overlay.tier)
                for field, values in result.values.items():
                    modified[field][sl]=values
                if result.delays is not None:
                    active_delays=np.isfinite(result.delays)
                    active_offsets=np.arange(start,start+count,dtype=np.int64)[active_delays]
                    replay_source_ids[active_offsets]=source_ids[sources[active_offsets]]
                    replay_delays[active_offsets]=result.delays[active_delays]
                _band=_episode_speed_band(seg,start,count)
                _freeze_src=int(source_ids[result.anchor_offset]) if (overlay.attack_family=="freeze_fixed_value" and result.anchor_offset is not None) else None
                episodes.append(dict(episode_id=eid,overlay_key=overlay.overlay_key,icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,onset_mode=overlay.onset_mode,duration_seconds_requested=overlay.duration_seconds,n_rows=count,start_row_offset=start,end_row_offset=start+count-1,start_time=int(times[start]),end_time=int(times[start+count-1]),start_source_row_id=int(source_ids[start]),end_source_row_id=int(source_ids[start+count-1]),grid_cell_id=_cell(seg.lat.iloc[start],seg.lon.iloc[start],grid_degrees),speed_band=_band,altitude_variant=overlay.altitude_variant,horizontal_magnitude_m=overlay.magnitude_m,bearing_deg=bearing,shared_altitude_shift_m=shift,gaussian_sigma_m=overlay.sigma_m,eq12_kappa=overlay.kappa,replay_delay_seconds_requested=overlay.replay_delay_s if sources is not None else None,replay_delay_seconds_effective=float(np.nanmedian(result.delays)) if result.delays is not None else None,freeze_anchor_source_row_id=_freeze_src,selection_method=method,tau_requested=overlay.tau,dataset_mode=overlay.dataset_mode,seed_derivation=f"sha256(global_seed|icao24|segment_id|selection|{overlay.overlay_key}); placement/episode/params independent",parameters_json=json.dumps(spec.__dict__,sort_keys=True),accepted=True,rejection_reason=None))
                changed_by_row = result.changed_fields
                changed_indices = np.fromiter((i for i, fields in enumerate(changed_by_row) if fields), dtype=np.int64)
                for offset in changed_indices:
                    fields = changed_by_row[offset]
                    provenance.append(dict(source_row_id=int(source_ids[start+offset]),episode_id=eid,changed_fields_json=strict_json(fields),orig_values_json=strict_json({f:float(seg[f].iloc[start+offset]) for f in fields}),mod_values_json=strict_json({f:float(result.values[f][offset]) for f in fields}),ramp_multiplier=np.float32(result.multipliers[offset]),validation_status="accepted"))

        attack_mask = multipliers > 0
        row_columns = {
            "row_id": source_ids, "source_row_id": source_ids,
            "icao24": seg.icao24.to_numpy(), "segment_id": seg.segment_id.to_numpy(np.int32),
            "time": times, "segment_row_offset": offsets, "split": np.full(len(seg), split, dtype=object),
        }
        for field in FEATURE_FIELDS:
            row_columns[f"orig_{field}"] = seg[field].to_numpy(dtype=float, copy=True)
            row_columns[f"mod_{field}"] = modified[field]
        row_columns.update({
            "onground": pd.array(seg.onground, dtype="boolean"),
            "contact_lag_seconds": seg.contact_lag_seconds.to_numpy(dtype=float),
            "contact_lag_missing": seg.contact_lag_missing.to_numpy(dtype=bool),
            "is_attack_row": attack_mask,
            "attack_family": episode_family, "attack_subtype": episode_subtype, "tier": episode_tier,
            "episode_id": _nullable_episode_ids(episode_ids),
            "episode_position": positions, "ramp_multiplier": multipliers.astype(np.float32),
            "replay_source_row_id": _nullable_source_ids(replay_source_ids),
            "replay_delay_seconds": replay_delays.astype(np.float32),
        })
        attacked.append(_table_from_columns("attacked_rows", row_columns))

        label_columns = {
            "source_row_id": source_ids,
            "episode_id": _nullable_episode_ids(episode_ids),
            "is_attack_row": attack_mask, "attack_family": episode_family,
            "attack_subtype": episode_subtype, "tier": episode_tier,
            "episode_position": positions, "ramp_multiplier": multipliers.astype(np.float32),
        }
        labels.append(_table_from_columns("step_labels", label_columns))

        for item in label_windows(multipliers,positions,episode_ids):
            eid=item["episode_id"]
            family,subtype,tier=meta.get(eid,(None,None,None))
            windows.append(dict(**item,icao24=icao24,segment_id=segment_id,split=split,attack_family=family,attack_subtype=subtype,tier=tier))

    frames = {
        "attacked_rows": pd.concat(attacked, ignore_index=True) if attacked else empty_table("attacked_rows"),
        "step_labels": pd.concat(labels, ignore_index=True) if labels else empty_table("step_labels"),
        "episodes": _table("episodes", episodes),
        "rejected_candidates": _table("rejected_candidates", rejected),
        "modified_row_provenance": _table("modified_row_provenance", provenance),
        "windows": _table("windows", windows),
        "segments": _table("segments", segments),
        "overlay_selections": _table("overlay_selections", overlay_selections),
    }
    out = AssembledTables(*(frames[name] for name in TABLE_NAMES))
    for name in TABLE_NAMES:
        validate_table(getattr(out,name),name)
    return out


def iter_assembled_chunks(
    df: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    grid_degrees: float = 5.0,
    max_segments_per_chunk: int = 64,
    chosen_segments: set | None = None,
):
    """Yield schema-validated tables for bounded groups of whole segments.

    The keyed input is retained in memory; assembled output is bounded by
    ``max_segments_per_chunk`` and can be written incrementally by the Stage 1
    writer. Segments are never split across yielded chunks. ``chosen_segments``
    (ranked quota mode) overrides the Bernoulli selection predicate.
    """
    if max_segments_per_chunk < 1:
        raise ValueError("max_segments_per_chunk must be at least one")
    keyed = add_natural_keys(df).sort_values(["icao24","segment_id","time"],kind="mergesort").reset_index(drop=True)
    group_start = keyed[["icao24","segment_id"]].ne(keyed[["icao24","segment_id"]].shift()).any(axis=1).to_numpy().nonzero()[0]
    if not len(group_start):
        yield _assemble_keyed(keyed,overlay,global_seed,split_of,grid_degrees,chosen_segments)
        return
    bounds = np.append(group_start, len(keyed))
    for first_group in range(0,len(group_start),max_segments_per_chunk):
        last_group = min(first_group+max_segments_per_chunk,len(group_start))
        chunk = keyed.iloc[bounds[first_group]:bounds[last_group]]
        yield _assemble_keyed(chunk,overlay,global_seed,split_of,grid_degrees,chosen_segments)


def assemble_overlay(
    df: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    grid_degrees: float = 5.0,
    max_segments_per_chunk: int = 64,
    chosen_segments: set | None = None,
) -> AssembledTables:
    """Assemble one validated overlay without reading config or writing files.

    Grid IDs use ``floor((median_lat+90)/degrees):floor((median_lon+180)/degrees)``.
    ``tau`` is Bernoulli selection probability over eligible aircraft-segments.
    Use :func:`iter_assembled_chunks` when writing large runs to bound output
    memory rather than retaining all seven output tables at once.
    """
    chunks = list(iter_assembled_chunks(df,overlay,global_seed,split_of,grid_degrees,max_segments_per_chunk,chosen_segments))
    frames = {}
    for name in TABLE_NAMES:
        parts = [getattr(chunk,name) for chunk in chunks]
        frames[name] = pd.concat(parts,ignore_index=True) if parts else empty_table(name)
    return AssembledTables(*(frames[name] for name in TABLE_NAMES))


def _merge_overlay_chunk(per_overlay, overlays) -> AssembledTables:
    """Resolve selected-overlay conflicts in sorted overlay-key order.

    ``segments`` is the final merged summary. Its selection detail describes
    the winning overlay when one was selected, otherwise the first eligible
    overlay (or the lexicographically first overlay if none are eligible).
    Complete per-overlay Bernoulli evidence lives in ``overlay_selections``.
    """
    overlay_order = sorted(overlays, key=lambda item: item.overlay_key)
    by_key = {item.overlay_key: tables for item, tables in zip(overlays, per_overlay)}
    selection_frames = [by_key[item.overlay_key].overlay_selections for item in overlay_order]
    all_selections = pd.concat(selection_frames, ignore_index=True)
    all_selections = all_selections.sort_values(["icao24", "segment_id", "overlay_key"], kind="mergesort").reset_index(drop=True)
    selection_by_segment = {
        (str(icao24), int(segment_id)): group.reset_index(drop=True)
        for (icao24, segment_id), group in all_selections.groupby(["icao24", "segment_id"], sort=False)
    }

    chosen_keys: dict[tuple[str, int], str | None] = {}
    representative_keys: dict[tuple[str, int], str] = {}
    for key, group in selection_by_segment.items():
        selected = group[group.selected]
        winner = str(selected.iloc[0].overlay_key) if not selected.empty else None
        chosen_keys[key] = winner
        if winner is not None:
            representative_keys[key] = winner
        else:
            eligible = group[group.eligible]
            representative_keys[key] = str((eligible.iloc[0] if not eligible.empty else group.iloc[0]).overlay_key)
    all_selections["chosen"] = [chosen_keys[(str(row.icao24), int(row.segment_id))] == row.overlay_key for row in all_selections.itertuples()]

    def indices_by_segment(frame: pd.DataFrame):
        if frame.empty:
            return {}
        return {
            (str(icao24), int(segment_id)): np.asarray(indices, dtype=np.int64)
            for (icao24, segment_id), indices in frame.groupby(["icao24", "segment_id"], sort=False).indices.items()
        }

    segment_indices = {}
    for overlay_key, tables in by_key.items():
        group_indices = {
            name: indices_by_segment(getattr(tables, name))
            for name in ("attacked_rows", "episodes", "rejected_candidates", "windows", "segments")
        }
        attacked_indices = group_indices["attacked_rows"]
        group_indices["step_labels"] = attacked_indices
        source_to_segment = {}
        for key, indices in attacked_indices.items():
            source_ids = tables.attacked_rows.iloc[indices].source_row_id.to_numpy(np.int64)
            source_to_segment.update((int(source_id), key) for source_id in source_ids)
        provenance_groups: dict[tuple[str, int], list[int]] = {}
        for index, source_id in enumerate(tables.modified_row_provenance.source_row_id.to_numpy(np.int64)):
            key = source_to_segment.get(int(source_id))
            if key is not None:
                provenance_groups.setdefault(key, []).append(index)
        group_indices["modified_row_provenance"] = {
            key: np.asarray(indices, dtype=np.int64) for key, indices in provenance_groups.items()
        }
        segment_indices[overlay_key] = group_indices

    output_parts = {name: [] for name in TABLE_NAMES if name != "overlay_selections"}
    for key, winner_key in chosen_keys.items():
        selected_key = winner_key or representative_keys[key]
        source_tables = by_key[selected_key]
        for name in output_parts:
            frame = getattr(source_tables, name)
            indices = segment_indices[selected_key][name].get(key)
            if indices is not None:
                output_parts[name].append(frame.iloc[indices])

        # Keep per-request accounting for every selected overlay that lost the
        # deterministic merge conflict. No placement/build attempt is made.
        if winner_key is not None:
            for overlay in overlay_order:
                if overlay.overlay_key == winner_key:
                    continue
                selection = selection_by_segment[key].loc[
                    selection_by_segment[key].overlay_key == overlay.overlay_key
                ].iloc[0]
                if not selection.selected:
                    continue
                base = by_key[overlay.overlay_key].segments
                segment_index = segment_indices[overlay.overlay_key]["segments"][key][0]
                segment = base.iloc[segment_index]
                n_rows = rows_for_duration(overlay.duration_seconds)
                output_parts["rejected_candidates"].append(_table(
                    "rejected_candidates",
                    [dict(candidate_id=_episode_id(key[0], key[1], request_index, overlay.overlay_key),
                          overlay_key=overlay.overlay_key,
                          icao24=key[0], segment_id=key[1], split=segment.split,
                          attack_family=overlay.attack_family,
                          attack_subtype=overlay.subtype or overlay.attack_family,
                          tier=overlay.tier, requested_start_row_offset=-1,
                          requested_n_rows=n_rows, stage="placement", reason="overlay_conflict",
                          details_json=strict_json({"winner_overlay_key": winner_key}))
                     for request_index in range(overlay.episodes_per_segment)]
                ))

    frames = {}
    for name, parts in output_parts.items():
        frame = pd.concat(parts, ignore_index=True) if parts else empty_table(name)
        sort_columns = {
            "attacked_rows": ["source_row_id"], "step_labels": ["source_row_id"],
            "episodes": ["icao24", "segment_id", "start_row_offset"],
            "rejected_candidates": ["icao24", "segment_id", "candidate_id"],
            "modified_row_provenance": ["source_row_id"],
            "windows": ["icao24", "segment_id", "start_offset"],
            "segments": ["icao24", "segment_id"],
        }[name]
        frames[name] = frame.sort_values(sort_columns, kind="mergesort").reset_index(drop=True) if not frame.empty else empty_table(name)

    # Build one merged segment summary. The exact evidence for each overlay is
    # in the eighth table, so a summary draw never stands in for all overlays.
    summaries = []
    for key, winner_key in chosen_keys.items():
        representative = representative_keys[key]
        row_index = segment_indices[representative]["segments"][key][0]
        row = by_key[representative].segments.iloc[row_index].to_dict()
        row["eligible"] = bool(selection_by_segment[key].eligible.any())
        row["selected"] = winner_key is not None
        summaries.append(row)
    frames["segments"] = _table("segments", summaries)
    frames["overlay_selections"] = all_selections
    out = AssembledTables(*(frames[name] for name in TABLE_NAMES))
    for name in TABLE_NAMES:
        validate_table(getattr(out, name), name)
    return out


def iter_assembled_multi_chunks(
    df: pd.DataFrame,
    overlays: tuple[OverlaySpec, ...] | list[OverlaySpec],
    global_seed: int,
    split_of: Callable[[str], str],
    grid_degrees: float = 5.0,
    max_segments_per_chunk: int = 64,
    chosen_segments: set | None = None,
):
    """Yield bounded merged chunks, enforcing the approved one-overlay rule.

    ``chosen_segments`` (ranked quota mode) is a set of
    ``(icao24, segment_id, overlay_key)`` applied to every overlay's per-segment
    selection; it overrides the Bernoulli predicate.
    """
    if not overlays:
        raise ValueError("at least one overlay is required")
    keys = [overlay.overlay_key for overlay in overlays]
    if len(set(keys)) != len(keys):
        raise ValueError("overlay keys must be unique")
    if max_segments_per_chunk < 1:
        raise ValueError("max_segments_per_chunk must be at least one")
    keyed = add_natural_keys(df).sort_values(["icao24", "segment_id", "time"], kind="mergesort").reset_index(drop=True)
    group_start = keyed[["icao24", "segment_id"]].ne(keyed[["icao24", "segment_id"]].shift()).any(axis=1).to_numpy().nonzero()[0]
    if not len(group_start):
        yield _merge_overlay_chunk([_assemble_keyed(keyed, overlay, global_seed, split_of, grid_degrees, chosen_segments) for overlay in overlays], overlays)
        return
    bounds = np.append(group_start, len(keyed))
    for first_group in range(0, len(group_start), max_segments_per_chunk):
        last_group = min(first_group + max_segments_per_chunk, len(group_start))
        chunk = keyed.iloc[bounds[first_group]:bounds[last_group]]
        pieces = [_assemble_keyed(chunk, overlay, global_seed, split_of, grid_degrees, chosen_segments) for overlay in overlays]
        yield _merge_overlay_chunk(pieces, overlays)


def assemble_overlays(
    df: pd.DataFrame,
    overlays: tuple[OverlaySpec, ...] | list[OverlaySpec],
    global_seed: int,
    split_of: Callable[[str], str],
    grid_degrees: float = 5.0,
    max_segments_per_chunk: int = 64,
    chosen_segments: set | None = None,
) -> AssembledTables:
    """Assemble multiple overlays with lexicographic conflict resolution."""
    chunks = list(iter_assembled_multi_chunks(df, overlays, global_seed, split_of, grid_degrees, max_segments_per_chunk, chosen_segments))
    frames = {}
    for name in TABLE_NAMES:
        parts = [getattr(chunk, name) for chunk in chunks]
        frames[name] = pd.concat(parts, ignore_index=True) if parts else empty_table(name)
    return AssembledTables(*(frames[name] for name in TABLE_NAMES))
