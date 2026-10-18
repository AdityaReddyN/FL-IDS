"""Read-only calibration for the proposed V3 Stage 1 design.

This script reads immutable inputs and writes only its requested JSON report under
docs/. The small oracle trial alters arrays in memory only; it writes no data,
episodes, manifests, or attack-generation artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


CORE = ["lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude"]
SPEED_BANDS = (("0_50", 0.0, 50.0), ("50_100", 50.0, 100.0), ("100_200", 100.0, 200.0), ("200_plus", 200.0, np.inf))
DT_BANDS = (("0_5", 0.0, 5.0), ("5_10", 5.0, 10.0), ("10_20", 10.0, 20.0), ("20_30", 20.0, 30.000001))
VERTICAL_BANDS = (("0_5", 0.0, 5.0), ("5_15", 5.0, 15.0), ("15_plus", 15.0, np.inf))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/opensky_clean_v1.parquet"))
    parser.add_argument("--splits", type=Path, default=Path("data/sequences_v2/split_aircraft.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/calibration_v3_stage1.json"))
    parser.add_argument("--max-contact-lag-seconds", type=float, default=30.0)
    parser.add_argument("--replay-delay-seconds", type=float, default=300.0)
    parser.add_argument("--replay-tolerance-seconds", type=float, default=5.0)
    parser.add_argument("--window-rows", type=int, default=30)
    parser.add_argument("--window-stride-rows", type=int, default=10)
    parser.add_argument("--minimum-attacked-rows", type=int, default=5)
    parser.add_argument("--episode-rows", type=int, default=12, help="120-second nominal episode at 10-second sampling.")
    parser.add_argument("--oracle-trial-size", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def native(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Cannot serialize {type(value)!r}")


def qs(values: np.ndarray, levels: tuple[float, ...] = (0.5, 0.9, 0.95, 0.99, 0.999)) -> dict[str, float | int | None]:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {"n": 0, **{f"q{str(level * 100).replace('.', '_')}": None for level in levels}}
    result: dict[str, float | int | None] = {"n": int(len(values))}
    for level in levels:
        result[f"q{str(level * 100).replace('.', '_')}"] = float(np.quantile(values, level))
    return result


def circular_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.abs((a - b + 180.0) % 360.0 - 180.0)


def add_split(df: pd.DataFrame, split_path: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    split_ids = json.loads(split_path.read_text(encoding="utf-8"))
    mapping = {str(icao): split for split, aircraft in split_ids.items() for icao in aircraft}
    df["split"] = df["icao24"].astype(str).map(mapping)
    source_aircraft = set(df["icao24"].astype(str).unique())
    split_aircraft = set(mapping)
    coverage = {
        "cleaned_aircraft": len(source_aircraft),
        "aircraft_in_split_file": len(split_aircraft),
        "cleaned_aircraft_covered": len(source_aircraft & split_aircraft),
        "cleaned_aircraft_missing_from_split": len(source_aircraft - split_aircraft),
        "split_aircraft_absent_from_cleaned": len(split_aircraft - source_aircraft),
    }
    if df["split"].isna().any():
        raise ValueError("Some cleaned rows are absent from split_aircraft.json")
    return df, coverage


def replay_links(df: pd.DataFrame, eligible: np.ndarray, delay: float, tolerance: float) -> np.ndarray:
    """Return source positions for same-aircraft/same-segment replay targets."""
    result = np.full(len(df), -1, dtype=np.int64)
    times = df["time"].to_numpy(dtype=float)
    for positions in df.groupby(["icao24", "segment_id"], sort=False).indices.values():
        positions = np.asarray(positions, dtype=np.int64)
        sources = positions[eligible[positions]]
        if len(sources) == 0:
            continue
        source_time = times[sources]
        desired = times[sources] - delay
        right = np.searchsorted(source_time, desired, side="left")
        left = np.clip(right - 1, 0, len(sources) - 1)
        right = np.clip(right, 0, len(sources) - 1)
        picked = np.where(np.abs(source_time[right] - desired) < np.abs(source_time[left] - desired), right, left)
        valid = (np.abs(source_time[picked] - desired) <= tolerance) & (source_time[picked] < times[sources])
        result[sources[valid]] = sources[picked[valid]]
    return result


def consecutive_members(df: pd.DataFrame, mask: np.ndarray, minimum: int) -> np.ndarray:
    """Keep rows that belong to a run of at least minimum true rows in a segment."""
    kept = np.zeros(len(mask), dtype=bool)
    for positions in df.groupby(["icao24", "segment_id"], sort=False).indices.values():
        positions = np.asarray(positions, dtype=np.int64)
        padded = np.r_[False, mask[positions], False].astype(np.int8)
        starts = np.flatnonzero(np.diff(padded) == 1)
        ends = np.flatnonzero(np.diff(padded) == -1)
        for start, end in zip(starts, ends):
            if end - start >= minimum:
                kept[positions[start:end]] = True
    return kept


def band_labels(values: np.ndarray, bands: tuple[tuple[str, float, float], ...]) -> np.ndarray:
    output = np.full(len(values), "outside", dtype=object)
    for name, lower, upper in bands:
        output[(values >= lower) & (values < upper)] = name
    return output


def residual_summary(values: np.ndarray, valid: np.ndarray, first_band: np.ndarray, second_band: np.ndarray) -> dict[str, dict[str, dict[str, float | int | None]]]:
    result: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for first in sorted(set(first_band[valid])):
        result[str(first)] = {}
        first_mask = valid & (first_band == first)
        for second in sorted(set(second_band[first_mask])):
            result[str(first)][str(second)] = qs(values[first_mask & (second_band == second)])
    return result


def count_window_overlap(segment_rows: int, episode_start: int, episode_rows: int, window_rows: int, stride: int, minimum_attacked: int, ramp_rows: int = 3) -> tuple[int, int]:
    """Return qualifying and interior-only window counts for an in-memory episode."""
    lower = episode_start + minimum_attacked - window_rows
    upper = episode_start + episode_rows - minimum_attacked
    first = max(0, int(np.ceil(lower / stride)) * stride)
    last = min(segment_rows - window_rows, int(np.floor(upper / stride)) * stride)
    qualifying = max(0, (last - first) // stride + 1)
    interior_first = max(0, int(np.ceil((episode_start + ramp_rows) / stride)) * stride)
    interior_last = min(segment_rows - window_rows, int(np.floor((episode_start + episode_rows - ramp_rows - window_rows) / stride)) * stride)
    interior_only = max(0, (interior_last - interior_first) // stride + 1)
    return qualifying, interior_only


def window_episode_distribution(df: pd.DataFrame, candidate: np.ndarray, episode_rows: int, window_rows: int, stride: int, minimum_attacked: int, seed: int) -> dict[str, object]:
    """Sample valid in-memory starts; no episodes or files are created."""
    counts: list[int] = []
    interior_counts: list[int] = []
    rng = np.random.default_rng(seed + episode_rows)
    groups = list(df.groupby(["icao24", "segment_id"], sort=False).indices.values())
    selected_groups = rng.choice(len(groups), size=min(1_000, len(groups)), replace=False)
    for group_index in selected_groups:
        positions = groups[group_index]
        positions = np.asarray(positions, dtype=np.int64)
        possible = candidate[positions]
        if len(positions) < episode_rows:
            continue
        prefix = np.r_[0, np.cumsum(possible, dtype=np.int32)]
        starts = np.flatnonzero(prefix[episode_rows:] - prefix[:-episode_rows] == episode_rows)
        if len(starts) > 50:
            starts = rng.choice(starts, size=50, replace=False)
        for start in starts:
            qualifying, interior_only = count_window_overlap(len(positions), int(start), episode_rows, window_rows, stride, minimum_attacked)
            counts.append(qualifying)
            interior_counts.append(interior_only)
    if not counts:
        return {"sampled_segments": len(selected_groups), "sampled_candidate_starts": 0, "windows_per_episode": qs(np.array([], dtype=float))}
    chosen_indices = rng.choice(np.arange(len(counts)), size=min(50_000, len(counts)), replace=False)
    chosen = np.asarray(counts)[chosen_indices]
    chosen_interior = np.asarray(interior_counts)[chosen_indices]
    evaluable = chosen[chosen > 0]
    return {
        "sampled_segments": len(selected_groups),
        "sampled_candidate_starts": len(counts),
        "sampled_starts": len(chosen),
        "windows_per_episode": {**qs(chosen.astype(float)), "min": int(chosen.min()), "max": int(chosen.max()), "mean": float(chosen.mean())},
        "windows_per_evaluable_episode": {**qs(evaluable.astype(float)), "min": int(evaluable.min()), "max": int(evaluable.max()), "mean": float(evaluable.mean())} if len(evaluable) else None,
        "interior_only_windows_per_episode": {**qs(chosen_interior.astype(float)), "min": int(chosen_interior.min()), "max": int(chosen_interior.max()), "mean": float(chosen_interior.mean())},
    }


def capacity_by_split_band(df: pd.DataFrame, mask: np.ndarray, speed_label: np.ndarray, maneuver: np.ndarray) -> dict[str, object]:
    compact = pd.DataFrame({"split": df["split"].to_numpy()[mask], "band": speed_label[mask], "icao24": df["icao24"].astype(str).to_numpy()[mask], "maneuver": maneuver[mask]})
    grouped = compact.groupby(["split", "band"], sort=False).agg(rows=("icao24", "size"), aircraft=("icao24", "nunique"))
    result: dict[str, object] = {}
    for split in ("train", "val", "test"):
        bands: dict[str, object] = {}
        for band in ("0_50", "50_100", "100_200", "200_plus"):
            value = grouped.loc[(split, band)] if (split, band) in grouped.index else None
            aircraft = int(value["aircraft"]) if value is not None else 0
            bands[band] = {
                "rows": int(value["rows"]) if value is not None else 0,
                "aircraft": aircraft,
                "test_band_descriptive_only_if_under_100_aircraft": bool(split == "test" and aircraft < 100),
            }
        maneuver_counts = compact.loc[compact["split"].eq(split), "maneuver"].value_counts().sort_index()
        result[split] = {"by_speed_band": bands, "maneuver_distribution": {str(k): int(v) for k, v in maneuver_counts.items()}}
    return result


def episode_start_capacity(df: pd.DataFrame, eligible_rows: np.ndarray, effect_rows: np.ndarray | None, speed_label: np.ndarray, episode_rows: int) -> dict[str, object]:
    """Count in-memory episode starts; no episodes are created or written."""
    output: dict[str, object] = {}
    for split in ("train", "val", "test"):
        by_band = {name: {"starts": 0, "aircraft": set(), "segments": set()} for name, _, _ in SPEED_BANDS}
        for (icao24, segment_id), positions in df.groupby(["icao24", "segment_id"], sort=False).indices.items():
            positions = np.asarray(positions, dtype=np.int64)
            if df["split"].iat[positions[0]] != split or len(positions) < episode_rows:
                continue
            prefix = np.r_[0, np.cumsum(eligible_rows[positions], dtype=np.int32)]
            starts = np.flatnonzero(prefix[episode_rows:] - prefix[:-episode_rows] == episode_rows)
            if effect_rows is not None:
                effect_prefix = np.r_[0, np.cumsum(effect_rows[positions], dtype=np.int32)]
                starts = starts[effect_prefix[starts + episode_rows] - effect_prefix[starts] >= 3]
            for start in starts:
                band = str(speed_label[positions[start]])
                if band in by_band:
                    item = by_band[band]
                    item["starts"] += 1
                    item["aircraft"].add(str(icao24))
                    item["segments"].add((str(icao24), int(segment_id)))
        output[split] = {band: {"episode_starts": item["starts"], "aircraft": len(item["aircraft"]), "segments": len(item["segments"])} for band, item in by_band.items()}
    return output


def oracle_rate(residual: np.ndarray, threshold: np.ndarray, selected: np.ndarray) -> float | None:
    return float((residual[selected] >= threshold[selected]).mean()) if len(selected) else None


def oracle_boundary_trials(north: np.ndarray, east: np.ndarray, expected_north: np.ndarray, expected_east: np.ndarray, threshold: np.ndarray, pair: np.ndarray, replay_pair: np.ndarray, replay_shift_north: np.ndarray, replay_shift_east: np.ndarray, size: int, seed: int) -> dict[str, object]:
    """In-memory residual oracle trials; no source table or attack output is edited."""
    rng = np.random.default_rng(seed)
    base = rng.choice(np.flatnonzero(pair), size=min(size, int(pair.sum())), replace=False)
    replay = rng.choice(np.flatnonzero(replay_pair), size=min(size, int(replay_pair.sum())), replace=False)
    base_natural = np.hypot(north - expected_north, east - expected_east)
    tiers = {"subtle": 500.0, "moderate": 2500.0, "blatant": 5500.0, "gross_positive_control": 11000.0}
    bearings = rng.uniform(0.0, 2.0 * np.pi, size=len(base))
    manipulation: dict[str, object] = {}
    for onset, multiplier in (("default_3_step_ramp", 1.0 / 3.0), ("abrupt", 1.0)):
        onset_results: dict[str, object] = {}
        for name, magnitude in tiers.items():
            residual = np.hypot(north[base] + multiplier * magnitude * np.cos(bearings) - expected_north[base], east[base] + multiplier * magnitude * np.sin(bearings) - expected_east[base])
            onset_results[name] = {"effect_meters": magnitude * multiplier, "recall": float((residual >= threshold[base]).mean())}
        manipulation[onset] = onset_results
    freeze: dict[str, object] = {}
    for onset, keep_current in (("default_3_step_ramp", 2.0 / 3.0), ("abrupt", 0.0)):
        residual = np.hypot(keep_current * north[base] - expected_north[base], keep_current * east[base] - expected_east[base])
        freeze[onset] = {name: {"duration_seconds": duration, "recall": float((residual >= threshold[base]).mean())} for name, duration in (("subtle", 90), ("moderate", 120), ("blatant", 180), ("gross_positive_control", 300))}
    partial: dict[str, object] = {}
    for onset, multiplier in (("default_3_step_ramp", 1.0 / 3.0), ("abrupt", 1.0)):
        residual = np.hypot(north[replay] + multiplier * replay_shift_north[replay] - expected_north[replay], east[replay] + multiplier * replay_shift_east[replay] - expected_east[replay])
        partial[onset] = {"delay_seconds": 300, "recall": float((residual >= threshold[replay]).mean())}
    return {
        "trial_rows": {"manipulation_freeze": int(len(base)), "partial_replay": int(len(replay))},
        "detector": "train_split_speed_band_p95_horizontal_residual",
        "manipulation": manipulation,
        "freeze": freeze,
        "partial_replay": partial,
        "false_positive_rate_on_maneuver_matched_controls": {
            "manipulation_freeze_clean_pairs": oracle_rate(base_natural, threshold, base),
            "partial_replay_matched_clean_pairs": oracle_rate(base_natural, threshold, replay),
        },
    }


def main() -> None:
    args = parse_args()
    columns = ["icao24", "segment_id", "time", "onground", "contact_lag_seconds", *CORE]
    print("Reading immutable cleaned table...", flush=True)
    df = pd.read_parquet(args.input, columns=columns).sort_values(["icao24", "segment_id", "time"]).reset_index(drop=True)
    df, split_coverage = add_split(df, args.splits)
    groups = df.groupby(["icao24", "segment_id"], sort=False)

    lag = df["contact_lag_seconds"].to_numpy(dtype=float)
    airborne = ~df["onground"].fillna(False).astype(bool).to_numpy()
    observed = df[CORE].notna().all(axis=1).to_numpy()
    eligibility = airborne & np.isfinite(lag) & (lag >= 0.0) & (lag <= args.max_contact_lag_seconds) & observed

    lat = df["lat"].to_numpy(dtype=float)
    lon = df["lon"].to_numpy(dtype=float)
    velocity = df["velocity"].to_numpy(dtype=float)
    heading = df["heading"].to_numpy(dtype=float)
    vertrate = df["vertrate"].to_numpy(dtype=float)
    baro = df["baroaltitude"].to_numpy(dtype=float)
    geo = df["geoaltitude"].to_numpy(dtype=float)
    previous_time = groups["time"].shift().to_numpy(dtype=float)
    previous_lat = groups["lat"].shift().to_numpy(dtype=float)
    previous_lon = groups["lon"].shift().to_numpy(dtype=float)
    previous_baro = groups["baroaltitude"].shift().to_numpy(dtype=float)
    previous_geo = groups["geoaltitude"].shift().to_numpy(dtype=float)
    previous_eligible = pd.Series(eligibility).groupby([df["icao24"], df["segment_id"]], sort=False).shift().fillna(False).to_numpy(dtype=bool)
    dt = df["time"].to_numpy(dtype=float) - previous_time
    pair = eligibility & previous_eligible & (dt > 0.0) & (dt <= 30.0)

    north = (lat - previous_lat) * 111_320.0
    east = (lon - previous_lon) * 111_320.0 * np.cos(np.deg2rad((lat + previous_lat) / 2.0))
    expected = velocity * dt
    expected_north = expected * np.cos(np.deg2rad(heading))
    expected_east = expected * np.sin(np.deg2rad(heading))
    horizontal_residual = np.hypot(north - expected_north, east - expected_east)
    speed_label = band_labels(velocity, SPEED_BANDS)
    dt_label = band_labels(dt, DT_BANDS)
    residual_by_dt_speed = residual_summary(horizontal_residual, pair, dt_label, speed_label)
    train_rows = df["split"].eq("train").to_numpy()
    speed_threshold_all = {band: float(np.quantile(horizontal_residual[pair & (speed_label == band)], 0.95)) for band, _, _ in SPEED_BANDS}
    speed_threshold = {band: float(np.quantile(horizontal_residual[pair & train_rows & (speed_label == band)], 0.95)) for band, _, _ in SPEED_BANDS}
    threshold = np.array([speed_threshold.get(str(label), np.inf) for label in speed_label], dtype=float)

    vertical_band = band_labels(np.abs(vertrate), VERTICAL_BANDS)
    baro_residual = np.abs((baro - previous_baro) - vertrate * dt)
    geo_residual = np.abs((geo - previous_geo) - vertrate * dt)
    altitude_valid = pair & np.isfinite(previous_baro) & np.isfinite(previous_geo)
    altitude = {
        "baroaltitude": residual_summary(baro_residual, altitude_valid, vertical_band, dt_label),
        "geoaltitude": residual_summary(geo_residual, altitude_valid, vertical_band, dt_label),
    }
    altitude_threshold_comparison = {}
    for name, values in (("baroaltitude", baro_residual), ("geoaltitude", geo_residual)):
        altitude_threshold_comparison[name] = {}
        for band, _, _ in VERTICAL_BANDS:
            all_values = values[altitude_valid & (vertical_band == band)]
            train_values = values[altitude_valid & train_rows & (vertical_band == band)]
            altitude_threshold_comparison[name][band] = {"all_data_p95": float(np.quantile(all_values, .95)), "train_only_p95": float(np.quantile(train_values, .95)), "difference_train_minus_all": float(np.quantile(train_values, .95) - np.quantile(all_values, .95))}
    geo_threshold = float(np.quantile(geo_residual[altitude_valid & train_rows], 0.999))
    geo_glitch = altitude_valid & (geo_residual > geo_threshold)

    prior = replay_links(df, eligibility, args.replay_delay_seconds, args.replay_tolerance_seconds)
    replay_eligible = prior >= 0
    previous_prior = pd.Series(prior).groupby([df["icao24"], df["segment_id"]], sort=False).shift().fillna(-1).to_numpy(dtype=np.int64)
    replay_pair = replay_eligible & (previous_prior >= 0) & pair
    target = np.flatnonzero(replay_eligible)
    source = prior[target]
    changed_speed = np.zeros(len(df), dtype=bool)
    changed_heading = np.zeros(len(df), dtype=bool)
    changed_vertical = np.zeros(len(df), dtype=bool)
    changed_speed[target] = np.abs(velocity[target] - velocity[source]) >= 1.0
    changed_heading[target] = circular_difference(heading[target], heading[source]) >= 1.0
    changed_vertical[target] = np.abs(vertrate[target] - vertrate[source]) >= 0.5
    measurable = changed_speed | changed_heading | changed_vertical
    maneuver = np.full(len(df), "none", dtype=object)
    for index in target:
        flags = [name for name, value in (("speed", changed_speed[index]), ("heading", changed_heading[index]), ("vertical_rate", changed_vertical[index])) if value]
        maneuver[index] = "+".join(flags) if flags else "none"

    source_previous = previous_prior[replay_pair]
    current = np.flatnonzero(replay_pair)
    source_north = (lat[prior[current]] - lat[source_previous]) * 111_320.0
    source_east = (lon[prior[current]] - lon[source_previous]) * 111_320.0 * np.cos(np.deg2rad((lat[prior[current]] + lat[source_previous]) / 2.0))
    partial_residual = np.full(len(df), np.nan)
    partial_residual[current] = np.hypot(source_north - expected_north[current], source_east - expected_east[current])
    partial_effect_row = replay_pair & measurable & (partial_residual >= threshold)
    partial_gated = consecutive_members(df, partial_effect_row, minimum=3)
    replay_shift_north = np.zeros(len(df), dtype=float)
    replay_shift_east = np.zeros(len(df), dtype=float)
    replay_shift_north[current] = (lat[prior[current]] - lat[current]) * 111_320.0
    replay_shift_east[current] = (lon[prior[current]] - lon[current]) * 111_320.0 * np.cos(np.deg2rad(lat[current]))

    manipulation_tiers = {"subtle": 500.0, "moderate": 2500.0, "blatant": 5500.0, "gross_positive_control": 11000.0}
    manipulation_gate = {name: pair & (magnitude / 3.0 >= threshold) for name, magnitude in manipulation_tiers.items()}
    gradual_gate = {name: {"per_step_drift": pair & (magnitude / 59.0 >= threshold), "cumulative_offset": pair & (magnitude >= threshold)} for name, magnitude in manipulation_tiers.items()}
    gaussian_gate = {name: pair & (sigma >= threshold) for name, sigma in (("subtle", 250.0), ("moderate", 1250.0), ("blatant", 2750.0), ("gross_positive_control", 5500.0))}
    freeze_gate = pair & (expected >= threshold)

    def count(mask: np.ndarray) -> dict[str, int]:
        return {"rows": int(mask.sum()), "segments": int(df.loc[mask, ["icao24", "segment_id"]].drop_duplicates().shape[0]), "aircraft": int(df.loc[mask, "icao24"].nunique())}

    long_600 = window_episode_distribution(df, eligibility, 60, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed)
    long_900 = window_episode_distribution(df, eligibility, 90, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed)
    episode_distribution = {
        "replay_120_seconds_nominal": window_episode_distribution(df, replay_eligible, args.episode_rows, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed),
        "freeze_duration_rows": {
            "90_seconds": window_episode_distribution(df, eligibility, 9, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed),
            "600_seconds_long": long_600,
            "900_seconds_long": long_900,
        },
        "manipulation_long_episode_rows": {
            "600_seconds": long_600,
            "900_seconds": long_900,
        },
    }

    report = {
        "report_version": 3,
        "read_only": True,
        "input": str(args.input).replace("\\", "/"),
        "split_file": str(args.splits).replace("\\", "/"),
        "parameters": {"replay_delay_seconds": args.replay_delay_seconds, "replay_tolerance_seconds": args.replay_tolerance_seconds, "window_rows": args.window_rows, "window_stride_rows": args.window_stride_rows, "minimum_attacked_rows": args.minimum_attacked_rows, "truth_rule": "at least 5 attacked rows; detectability is reported separately", "reporting_gate": "attack-specific quantity compared to train-split speed-band p95; not used to generate the primary dataset"},
        "split_aircraft_coverage": split_coverage,
        "horizontal_residual_meters_by_dt_then_speed_band": residual_by_dt_speed,
        "speed_band_p95_threshold_meters": {"train_only": speed_threshold, "all_data": speed_threshold_all, "difference_train_minus_all": {band: speed_threshold[band] - speed_threshold_all[band] for band in speed_threshold}},
        "altitude_residual_meters_by_vertical_rate_then_dt": altitude,
        "altitude_p95_threshold_comparison_meters": altitude_threshold_comparison,
        "geoaltitude_glitch_screen": {"rule": "absolute(altitude_change - vertical_rate*dt) > global q99.9", "threshold_meters": geo_threshold, "rows": int(geo_glitch.sum())},
        "replay": {
            "eligibility_only": count(replay_eligible),
            "partial_field_ungated_pair": count(replay_pair),
            "partial_field_full_effect_gate": count(partial_gated),
            "full_field": {"reporting": "ungated eligibility and boundary-stratified results only; no interior residual gate is scientifically valid", "eligibility_only": count(replay_eligible)},
            "capacity_by_split_speed_band_replay_subtype": {
                "partial_field_ungated": {"rows": capacity_by_split_band(df, replay_pair, speed_label, maneuver)},
                "partial_field_gated": {"rows": capacity_by_split_band(df, partial_gated, speed_label, maneuver), "episode_starts_120_seconds": episode_start_capacity(df, replay_eligible, partial_gated, speed_label, args.episode_rows)},
                "full_field_eligibility_only": {"rows": capacity_by_split_band(df, replay_eligible & pair, speed_label, maneuver)},
            },
        },
        "manipulation_and_freeze_capacity_by_split_speed_band": {
            "shared_eligibility": capacity_by_split_band(df, pair, speed_label, np.full(len(df), "eligible", dtype=object)),
            "freeze_post_reporting_gate_v_times_dt": capacity_by_split_band(df, freeze_gate, speed_label, np.full(len(df), "freeze_gate", dtype=object)),
            "constant_default_3_step_ramp_post_gate": {name: capacity_by_split_band(df, mask, speed_label, np.full(len(df), "constant_gate", dtype=object)) for name, mask in manipulation_gate.items()},
            "gradual_600_second_post_gate": {name: {metric: capacity_by_split_band(df, mask, speed_label, np.full(len(df), metric, dtype=object)) for metric, mask in metrics.items()} for name, metrics in gradual_gate.items()},
            "gaussian_sigma_post_gate": {name: capacity_by_split_band(df, mask, speed_label, np.full(len(df), "gaussian_gate", dtype=object)) for name, mask in gaussian_gate.items()},
        },
        "windows_per_episode": episode_distribution,
        "oracle_boundary_trial": oracle_boundary_trials(north, east, expected_north, expected_east, threshold, pair, replay_pair & measurable, replay_shift_north, replay_shift_east, args.oracle_trial_size, args.seed),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=native) + "\n", encoding="utf-8")
    print(f"Wrote read-only calibration report: {args.output}")
    print(f"Replay eligible={report['replay']['eligibility_only']['rows']}; partial-field gated={report['replay']['partial_field_full_effect_gate']['rows']}")
    print(f"Geo glitch threshold={geo_threshold:.3f} m; rows={int(geo_glitch.sum())}")


if __name__ == "__main__":
    main()
