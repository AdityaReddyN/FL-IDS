"""Pure, in-memory assembly of one row-level Stage 1 overlay (D-025)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .eligibility import REQUIRED_FIELDS, eligible_starts, pair_valid, replay_source_offsets, row_eligible
from .episode import EpisodeSpec, HORIZONTAL_FAMILIES, REPLAY_FAMILIES, build_episode
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


@dataclass(frozen=True)
class AssembledTables:
    attacked_rows: pd.DataFrame; step_labels: pd.DataFrame; episodes: pd.DataFrame
    rejected_candidates: pd.DataFrame; modified_row_provenance: pd.DataFrame
    windows: pd.DataFrame; segments: pd.DataFrame


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


def _episode_id(icao24, segment_id, index):
    value = int.from_bytes(hashlib.sha256(f"{icao24}|{segment_id}|{index}".encode()).digest()[:8], "big")
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


def _legacy_nullable_episode_ids(values):
    """Preserve the pre-vectorization float64 coercion of nullable row IDs.

    The old record-to-DataFrame path first represented ``None``-containing
    int63 episode IDs as float64, which can round values above 2**53. Stage B
    keeps that serialized behavior bit-identical; changing it needs a separate
    artifact-version decision.
    """
    as_float = np.where(values >= 0, values.astype(np.float64), np.nan)
    return pd.Series(as_float).astype("Int64").array


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


def _assemble_keyed(
    keyed: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    grid_degrees: float,
) -> AssembledTables:
    """Assemble already-keyed rows; row/step tables are built column-wise."""
    attacked=[]; labels=[]; episodes=[]; rejected=[]; provenance=[]; windows=[]; segments=[]
    n_rows = rows_for_duration(overlay.duration_seconds)
    for (icao24, segment_id), seg in keyed.groupby(["icao24", "segment_id"], sort=True):
        seg = seg.reset_index(drop=True)
        times = seg.time.to_numpy(np.int64)
        source_ids = seg.source_row_id.to_numpy(np.int64)
        offsets = seg.segment_row_offset.to_numpy(np.int32)
        split = split_of(icao24)
        row_ok = row_eligible(seg, _required(overlay))
        sources = None
        if overlay.attack_family in REPLAY_FAMILIES:
            sources = replay_source_offsets(times, row_ok, overlay.replay_delay_s, overlay.replay_tolerance_s)
            row_ok &= sources >= 0
        if overlay.altitude_variant == "baro_plus_geo" and overlay.geoaltitude_glitch_threshold_m is not None:
            glitch = np.zeros(len(seg), dtype=bool)
            glitch[1:] = np.abs(np.diff(seg.geoaltitude.to_numpy(float))) > overlay.geoaltitude_glitch_threshold_m
            row_ok &= ~glitch
        starts = eligible_starts(seg, n_rows, row_ok, pair_valid(seg))
        starts, _ = filter_starts_by_span(starts, times, n_rows, overlay.duration_seconds)
        eligible = bool(len(starts))
        u = float(overlay_selection_rng(global_seed, icao24, segment_id, overlay.overlay_key).random())
        selected = eligible and u < overlay.tau
        segments.append(dict(icao24=icao24, segment_id=segment_id, split=split, n_rows=len(seg), cell_id=_cell(_finite_median(seg.lat), _finite_median(seg.lon), grid_degrees), n_eligible_starts=len(starts), eligible=eligible, selection_u=u, selected=selected))

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
                rejected.append(dict(candidate_id=_episode_id(icao24,segment_id,k),icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,requested_start_row_offset=-1,requested_n_rows=n_rows,stage="placement",reason=reason,details_json="{}"))
            for k,start,count in accepted:
                prng=parameter_rng(global_seed,icao24,segment_id,k)
                bearing=float(prng.uniform(0,360)) if overlay.attack_family in HORIZONTAL_FAMILIES else None
                shift=(1 if prng.integers(2) else -1)*(overlay.shift_m or 0) if overlay.attack_family=="altitude_constant_deviation" else overlay.shift_m
                spec=EpisodeSpec(overlay.attack_family,overlay.tier,overlay.subtype,overlay.altitude_variant,overlay.onset_mode,overlay.ramp_rows,overlay.magnitude_m,bearing,overlay.sigma_m,overlay.kappa,overlay.per_step_sigma_m,shift,overlay.replay_delay_s,overlay.replay_tolerance_s)
                result=build_episode({f:seg[f].to_numpy(float) for f in FEATURE_FIELDS},times,row_ok,sources,start,count,spec,episode_rng(global_seed,icao24,segment_id,k))
                eid=_episode_id(icao24,segment_id,k)
                if not result.accepted:
                    rejected.append(dict(candidate_id=eid,icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,requested_start_row_offset=start,requested_n_rows=count,stage="build",reason=result.reason,details_json=json.dumps(result.summary,sort_keys=True)))
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
                episodes.append(dict(episode_id=eid,icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,onset_mode=overlay.onset_mode,duration_seconds_requested=overlay.duration_seconds,n_rows=count,start_row_offset=start,end_row_offset=start+count-1,start_time=int(times[start]),end_time=int(times[start+count-1]),start_source_row_id=int(source_ids[start]),end_source_row_id=int(source_ids[start+count-1]),grid_cell_id=_cell(seg.lat.iloc[start],seg.lon.iloc[start],grid_degrees),speed_band="unknown",altitude_variant=overlay.altitude_variant,horizontal_magnitude_m=overlay.magnitude_m,bearing_deg=bearing,shared_altitude_shift_m=shift,gaussian_sigma_m=overlay.sigma_m,eq12_kappa=overlay.kappa,replay_delay_seconds_requested=overlay.replay_delay_s if sources is not None else None,replay_delay_seconds_effective=float(np.nanmedian(result.delays)) if result.delays is not None else None,freeze_anchor_source_row_id=None,selection_method="bernoulli_overlay_keyed_eligible_segment",tau_requested=overlay.tau,dataset_mode=overlay.dataset_mode,seed_derivation=f"sha256(global_seed|icao24|segment_id|selection|{overlay.overlay_key}); placement/episode/params independent",parameters_json=json.dumps(spec.__dict__,sort_keys=True),accepted=True,rejection_reason=None))
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
            "onground": seg.onground.to_numpy(dtype=bool),
            "contact_lag_seconds": seg.contact_lag_seconds.to_numpy(dtype=float),
            "contact_lag_missing": seg.contact_lag_missing.to_numpy(dtype=bool),
            "is_attack_row": attack_mask,
            "attack_family": episode_family, "attack_subtype": episode_subtype, "tier": episode_tier,
            "episode_id": _legacy_nullable_episode_ids(episode_ids),
            "episode_position": positions, "ramp_multiplier": multipliers.astype(np.float32),
            "replay_source_row_id": _nullable_source_ids(replay_source_ids),
            "replay_delay_seconds": replay_delays.astype(np.float32),
        })
        attacked.append(_table_from_columns("attacked_rows", row_columns))

        label_columns = {
            "source_row_id": source_ids,
            "episode_id": _legacy_nullable_episode_ids(episode_ids),
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
):
    """Yield schema-validated tables for bounded groups of whole segments.

    The keyed input is retained in memory; assembled output is bounded by
    ``max_segments_per_chunk`` and can be written incrementally by the Stage 1
    writer. Segments are never split across yielded chunks.
    """
    if max_segments_per_chunk < 1:
        raise ValueError("max_segments_per_chunk must be at least one")
    keyed = add_natural_keys(df).sort_values(["icao24","segment_id","time"],kind="mergesort").reset_index(drop=True)
    group_start = keyed[["icao24","segment_id"]].ne(keyed[["icao24","segment_id"]].shift()).any(axis=1).to_numpy().nonzero()[0]
    if not len(group_start):
        yield _assemble_keyed(keyed,overlay,global_seed,split_of,grid_degrees)
        return
    bounds = np.append(group_start, len(keyed))
    for first_group in range(0,len(group_start),max_segments_per_chunk):
        last_group = min(first_group+max_segments_per_chunk,len(group_start))
        chunk = keyed.iloc[bounds[first_group]:bounds[last_group]]
        yield _assemble_keyed(chunk,overlay,global_seed,split_of,grid_degrees)


def assemble_overlay(
    df: pd.DataFrame,
    overlay: OverlaySpec,
    global_seed: int,
    split_of: Callable[[str], str],
    grid_degrees: float = 5.0,
    max_segments_per_chunk: int = 64,
) -> AssembledTables:
    """Assemble all seven validated tables without reading config or writing files.

    Grid IDs use ``floor((median_lat+90)/degrees):floor((median_lon+180)/degrees)``.
    ``tau`` is Bernoulli selection probability over eligible aircraft-segments.
    Use :func:`iter_assembled_chunks` when writing large runs to bound output
    memory rather than retaining all seven output tables at once.
    """
    chunks = list(iter_assembled_chunks(df,overlay,global_seed,split_of,grid_degrees,max_segments_per_chunk))
    frames = {}
    for name in TABLE_NAMES:
        parts = [getattr(chunk,name) for chunk in chunks]
        frames[name] = pd.concat(parts,ignore_index=True) if parts else empty_table(name)
    return AssembledTables(*(frames[name] for name in TABLE_NAMES))
