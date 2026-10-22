"""Descriptive physical-plausibility metrics for generated row-level attacks.

Thresholds are intentionally not used for pass/fail because no cutoffs have
been approved for these reports. This is an implementation/diagnostic choice.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schemas import FEATURE_FIELDS


UNAVAILABLE_CHECKS = (
    "RF replay fidelity",
    "raw ADS-B bit-level effects",
    "receiver signal strength and receiver-side processing",
    "multi-receiver multilateration consistency",
)


def _summary(values) -> dict:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if not finite.size:
        return {"count": 0, "median": None, "p95": None, "max": None}
    return {
        "count": int(finite.size),
        "median": float(np.median(finite)),
        "p95": float(np.percentile(finite, 95)),
        "max": float(np.max(finite)),
    }


def _missing_fraction(group: pd.DataFrame, start: int, end: int) -> dict:
    phases = {
        "before": group.segment_row_offset.to_numpy() < start,
        "during": (group.segment_row_offset.to_numpy() >= start)
        & (group.segment_row_offset.to_numpy() <= end),
        "after": group.segment_row_offset.to_numpy() > end,
    }
    output = {}
    for phase, mask in phases.items():
        output[phase] = {
            field: (float(group.loc[mask, f"orig_{field}"].isna().mean()) if mask.any() else None)
            for field in FEATURE_FIELDS
        }
    return output


def _episode_metrics(group: pd.DataFrame, start: int, end: int) -> dict:
    group = group.sort_values("segment_row_offset", kind="mergesort").reset_index(drop=True)
    offsets = group.segment_row_offset.to_numpy(dtype=np.int64)
    times = group.time.to_numpy(dtype=np.float64)
    lat = group.mod_lat.to_numpy(dtype=float, na_value=np.nan)
    lon = group.mod_lon.to_numpy(dtype=float, na_value=np.nan)
    velocity = group.mod_velocity.to_numpy(dtype=float, na_value=np.nan)
    heading = group.mod_heading.to_numpy(dtype=float, na_value=np.nan)
    vertrate = group.mod_vertrate.to_numpy(dtype=float, na_value=np.nan)
    baro = group.mod_baroaltitude.to_numpy(dtype=float, na_value=np.nan)
    geo = group.mod_geoaltitude.to_numpy(dtype=float, na_value=np.nan)

    dt = np.diff(times)
    midlat = np.deg2rad((lat[:-1] + lat[1:]) / 2.0)
    dlat = lat[1:] - lat[:-1]
    dlon = (lon[1:] - lon[:-1] + 180.0) % 360.0 - 180.0
    distance = np.hypot(dlat * 111_320.0, dlon * 111_320.0 * np.cos(midlat))
    valid_pair = (dt > 0) & np.isfinite(dt) & np.isfinite(distance)
    implied_speed = np.divide(distance, dt, out=np.full_like(distance, np.nan), where=valid_pair)
    reported_speed = (velocity[:-1] + velocity[1:]) / 2.0
    heading_delta = (heading[1:] - heading[:-1] + 180.0) % 360.0 - 180.0
    turn_rate = np.divide(heading_delta, dt, out=np.full_like(dt, np.nan), where=(dt > 0) & np.isfinite(heading_delta))
    baro_rate = np.divide(np.diff(baro), dt, out=np.full_like(dt, np.nan), where=(dt > 0) & np.isfinite(baro[:-1]) & np.isfinite(baro[1:]))
    geo_rate = np.divide(np.diff(geo), dt, out=np.full_like(dt, np.nan), where=(dt > 0) & np.isfinite(geo[:-1]) & np.isfinite(geo[1:]))
    reported_vrate = (vertrate[:-1] + vertrate[1:]) / 2.0
    acceleration = np.divide(np.diff(velocity), dt, out=np.full_like(dt, np.nan), where=(dt > 0) & np.isfinite(velocity[:-1]) & np.isfinite(velocity[1:]))
    destinations = offsets[1:]
    continuity_masks = {
        "before": destinations < start,
        "during": (destinations > start) & (destinations <= end),
        "after": destinations > end + 1,
    }
    start_pair = destinations == start
    end_pair = destinations == end + 1
    return {
        "implied_ground_speed_mps": _summary(implied_speed[valid_pair]),
        "reported_ground_speed_mps": _summary(reported_speed[valid_pair]),
        "implied_minus_reported_speed_mps": _summary((implied_speed - reported_speed)[valid_pair]),
        "acceleration_proxy_mps2": _summary(acceleration),
        "turn_rate_deg_per_s": _summary(turn_rate),
        "baro_vertical_rate_mps": _summary(baro_rate),
        "geo_vertical_rate_mps": _summary(geo_rate),
        "reported_vertical_rate_mps": _summary(reported_vrate),
        "baro_minus_reported_vertical_rate_mps": _summary(baro_rate - reported_vrate),
        "continuity_boundary_implied_speed_mps": {
            "episode_start": _summary(implied_speed[start_pair]),
            "episode_end": _summary(implied_speed[end_pair]),
        },
        "continuity_distance_m_by_phase": {
            phase: _summary(distance[mask & valid_pair])
            for phase, mask in continuity_masks.items()
        },
    }


def build_plausibility_report(
    attacked_rows: pd.DataFrame,
    episodes: pd.DataFrame,
    rejected_candidates: pd.DataFrame,
) -> dict:
    """Summarize kinematics, continuity, missingness, and rejections per episode."""
    episode_reports = []
    for episode in episodes.itertuples(index=False):
        group_mask = (attacked_rows.icao24 == episode.icao24) & (attacked_rows.segment_id == episode.segment_id)
        group = attacked_rows.loc[group_mask]
        start, end = int(episode.start_row_offset), int(episode.end_row_offset)
        rejected_segment = rejected_candidates.loc[
            (rejected_candidates.icao24 == episode.icao24)
            & (rejected_candidates.segment_id == episode.segment_id)
        ] if not rejected_candidates.empty else rejected_candidates
        reasons = rejected_segment.reason.value_counts().to_dict() if not rejected_segment.empty else {}
        episode_reports.append({
            "episode_id": int(episode.episode_id),
            "icao24": str(episode.icao24),
            "segment_id": int(episode.segment_id),
            "attack_family": str(episode.attack_family),
            "start_row_offset": start,
            "end_row_offset": end,
            "kinematics": _episode_metrics(group, start, end),
            "missing_fraction": _missing_fraction(group, start, end),
            "rejected_candidate_counts_by_reason_in_segment": {str(key): int(value) for key, value in reasons.items()},
        })
    return {
        "report_version": 1,
        "episode_count": len(episode_reports),
        "episodes": episode_reports,
        "threshold_validation": "descriptive_only_no_cutoffs_approved",
        "unavailable_checks": list(UNAVAILABLE_CHECKS),
    }
