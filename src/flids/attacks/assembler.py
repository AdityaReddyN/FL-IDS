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
from .seeding import episode_rng, parameter_rng, placement_rng, segment_rng
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
    geoaltitude_glitch_threshold_m: float | None = None
    min_gap_seconds: float = 600.0

    def __post_init__(self):
        if not 0 <= self.tau <= 1: raise ValueError("tau must be in [0, 1]")
        if not 1 <= self.episodes_per_segment <= 3: raise ValueError("episodes_per_segment must be in 1..3")
        if self.dataset_mode != "uniform_per_subairspace": raise ValueError("unsupported dataset_mode")


@dataclass(frozen=True)
class AssembledTables:
    attacked_rows: pd.DataFrame; step_labels: pd.DataFrame; episodes: pd.DataFrame
    rejected_candidates: pd.DataFrame; modified_row_provenance: pd.DataFrame
    windows: pd.DataFrame; segments: pd.DataFrame


def _cell(lat, lon, degrees):
    if not np.isfinite(lat) or not np.isfinite(lon): return "unknown"
    return f"{int(np.floor((lat + 90.) / degrees))}:{int(np.floor((lon + 180.) / degrees))}"


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


def assemble_overlay(df: pd.DataFrame, overlay: OverlaySpec, global_seed: int, split_of: Callable[[str], str], grid_degrees: float = 5.0) -> AssembledTables:
    """Assemble all seven validated tables without reading config or writing files.

    Grid IDs use ``floor((median_lat+90)/degrees):floor((median_lon+180)/degrees)``.
    ``tau`` is Bernoulli selection probability over eligible aircraft-segments.
    """
    keyed = add_natural_keys(df).sort_values(["icao24", "segment_id", "time"], kind="mergesort").reset_index(drop=True)
    attacked=[]; labels=[]; episodes=[]; rejected=[]; provenance=[]; windows=[]; segments=[]
    n_rows = rows_for_duration(overlay.duration_seconds)
    for (icao24, segment_id), seg in keyed.groupby(["icao24", "segment_id"], sort=True):
        seg = seg.reset_index(drop=True); times = seg.time.to_numpy(np.int64); split = split_of(icao24)
        row_ok = row_eligible(seg, _required(overlay)); sources = None
        if overlay.attack_family in REPLAY_FAMILIES:
            sources = replay_source_offsets(times, row_ok, overlay.replay_delay_s, overlay.replay_tolerance_s); row_ok &= sources >= 0
        if overlay.altitude_variant == "baro_plus_geo" and overlay.geoaltitude_glitch_threshold_m is not None:
            glitch = np.zeros(len(seg), dtype=bool); glitch[1:] = np.abs(np.diff(seg.geoaltitude.to_numpy(float))) > overlay.geoaltitude_glitch_threshold_m; row_ok &= ~glitch
        starts = eligible_starts(seg, n_rows, row_ok, pair_valid(seg)); starts, _ = filter_starts_by_span(starts, times, n_rows, overlay.duration_seconds)
        eligible = bool(len(starts)); u = float(segment_rng(global_seed, icao24, segment_id).random()); selected = eligible and u < overlay.tau
        segments.append(dict(icao24=icao24, segment_id=segment_id, split=split, n_rows=len(seg), cell_id=_cell(np.nanmedian(seg.lat), np.nanmedian(seg.lon), grid_degrees), n_eligible_starts=len(starts), eligible=eligible, selection_u=u, selected=selected))
        multi=np.zeros(len(seg)); pos=np.full(len(seg), "none", dtype=object); ids=np.full(len(seg), -1, dtype=np.int64); meta={}; modified={}; replay_info={}
        if selected:
            accepted, failures = place_episodes(starts, times, overlay.duration_seconds, overlay.episodes_per_segment, lambda k: placement_rng(global_seed, icao24, segment_id, k), max_per_segment=3, min_gap_seconds=overlay.min_gap_seconds)
            for k, reason in failures: rejected.append(dict(candidate_id=_episode_id(icao24,segment_id,k),icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,requested_start_row_offset=-1,requested_n_rows=n_rows,stage="placement",reason=reason,details_json="{}"))
            for k,start,count in accepted:
                prng=parameter_rng(global_seed,icao24,segment_id,k); bearing=float(prng.uniform(0,360)) if overlay.attack_family in HORIZONTAL_FAMILIES else None; shift=(1 if prng.integers(2) else -1)*(overlay.shift_m or 0) if overlay.attack_family=="altitude_constant_deviation" else overlay.shift_m
                spec=EpisodeSpec(overlay.attack_family,overlay.tier,overlay.subtype,overlay.altitude_variant,overlay.onset_mode,overlay.ramp_rows,overlay.magnitude_m,bearing,overlay.sigma_m,overlay.kappa,overlay.per_step_sigma_m,shift,overlay.replay_delay_s,overlay.replay_tolerance_s)
                result=build_episode({f:seg[f].to_numpy(float) for f in FEATURE_FIELDS},times,row_ok,sources,start,count,spec,episode_rng(global_seed,icao24,segment_id,k)); eid=_episode_id(icao24,segment_id,k)
                if not result.accepted:
                    rejected.append(dict(candidate_id=eid,icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,requested_start_row_offset=start,requested_n_rows=count,stage="build",reason=result.reason,details_json=json.dumps(result.summary,sort_keys=True))); continue
                sl=slice(start,start+count); multi[sl]=result.multipliers; pos[sl]=result.positions; ids[sl]=eid; meta[eid]=(overlay.attack_family,overlay.subtype or overlay.attack_family,overlay.tier)
                for offset in range(count):
                    modified[start + offset] = {field: float(values[offset]) for field, values in result.values.items()}
                    if result.delays is not None and np.isfinite(result.delays[offset]):
                        replay_info[start + offset] = (int(seg.source_row_id.iloc[sources[start + offset]]), float(result.delays[offset]))
                episodes.append(dict(episode_id=eid,icao24=icao24,segment_id=segment_id,split=split,attack_family=overlay.attack_family,attack_subtype=overlay.subtype or overlay.attack_family,tier=overlay.tier,onset_mode=overlay.onset_mode,duration_seconds_requested=overlay.duration_seconds,n_rows=count,start_row_offset=start,end_row_offset=start+count-1,start_time=int(times[start]),end_time=int(times[start+count-1]),start_source_row_id=int(seg.source_row_id[start]),end_source_row_id=int(seg.source_row_id[start+count-1]),grid_cell_id=_cell(seg.lat.iloc[start],seg.lon.iloc[start],grid_degrees),speed_band="unknown",altitude_variant=overlay.altitude_variant,horizontal_magnitude_m=overlay.magnitude_m,bearing_deg=bearing,shared_altitude_shift_m=shift,gaussian_sigma_m=overlay.sigma_m,eq12_kappa=overlay.kappa,replay_delay_seconds_requested=overlay.replay_delay_s if sources is not None else None,replay_delay_seconds_effective=float(np.nanmedian(result.delays)) if result.delays is not None else None,freeze_anchor_source_row_id=None,selection_method="uniform_per_subairspace",eta_requested=overlay.tau,dataset_mode=overlay.dataset_mode,seed_derivation="sha256(global_seed|icao24|segment_id); episode/params spawn_key=(k,)",parameters_json=json.dumps(spec.__dict__,sort_keys=True),accepted=True,rejection_reason=None))
                for offset, fields in enumerate(result.changed_fields):
                    if fields: provenance.append(dict(source_row_id=int(seg.source_row_id[start+offset]),episode_id=eid,changed_fields_json=strict_json(fields),orig_values_json=strict_json({f:float(seg[f].iloc[start+offset]) for f in fields}),mod_values_json=strict_json({f:float(result.values[f][offset]) for f in fields}),ramp_multiplier=np.float32(result.multipliers[offset]),validation_status="accepted"))
        for i,row in seg.iterrows():
            eid=int(ids[i]); family, subtype, tier=meta.get(eid,(None,None,None)); mods={f: float(row[f]) for f in FEATURE_FIELDS}
            mods.update(modified.get(i, {})); replay_id, replay_delay = replay_info.get(i, (None, None))
            attacked.append(dict(row_id=int(row.source_row_id),source_row_id=int(row.source_row_id),icao24=icao24,segment_id=segment_id,time=int(row.time),segment_row_offset=i,split=split,**{f"orig_{f}":float(row[f]) for f in FEATURE_FIELDS},**{f"mod_{f}":mods[f] for f in FEATURE_FIELDS},onground=bool(row.onground),contact_lag_seconds=float(row.contact_lag_seconds),contact_lag_missing=bool(row.contact_lag_missing),is_attack_row=bool(multi[i]>0),attack_family=family,attack_subtype=subtype,tier=tier,episode_id=eid if eid>=0 else None,episode_position=pos[i],ramp_multiplier=np.float32(multi[i]),replay_source_row_id=replay_id,replay_delay_seconds=replay_delay))
            labels.append(dict(source_row_id=int(row.source_row_id),episode_id=eid if eid>=0 else None,is_attack_row=bool(multi[i]>0),attack_family=family,attack_subtype=subtype,tier=tier,episode_position=pos[i],ramp_multiplier=np.float32(multi[i])))
        for item in label_windows(multi,pos,ids):
            eid=item["episode_id"]; family,subtype,tier=meta.get(eid,(None,None,None)); windows.append(dict(**item,icao24=icao24,segment_id=segment_id,split=split,attack_family=family,attack_subtype=subtype,tier=tier))
    out=AssembledTables(*[_table(name, records) for name,records in zip(TABLE_NAMES,[attacked,labels,episodes,rejected,provenance,windows,segments])])
    for name in TABLE_NAMES: validate_table(getattr(out,name),name)
    return out
