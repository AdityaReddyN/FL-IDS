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


def count_window_overlap(segment_rows: int, episode_start: int, episode_rows: int, window_rows: int, stride: int, minimum_attacked: int) -> int:
    """Number of fixed-grid windows with enough overlap with an in-memory episode."""
    lower = episode_start + minimum_attacked - window_rows
    upper = episode_start + episode_rows - minimum_attacked
    first = max(0, int(np.ceil(lower / stride)) * stride)
    last = min(segment_rows - window_rows, int(np.floor(upper / stride)) * stride)
    return max(0, (last - first) // stride + 1)


def window_episode_distribution(df: pd.DataFrame, candidate: np.ndarray, episode_rows: int, window_rows: int, stride: int, minimum_attacked: int, seed: int) -> dict[str, object]:
    """Sample valid in-memory start positions; no episodes or files are created."""
    counts: list[int] = []
    for positions in df.groupby(["icao24", "segment_id"], sort=False).indices.values():
        positions = np.asarray(positions, dtype=np.int64)
        possible = candidate[positions]
        if len(positions) < episode_rows:
            continue
        prefix = np.r_[0, np.cumsum(possible, dtype=np.int32)]
        starts = np.flatnonzero(prefix[episode_rows:] - prefix[:-episode_rows] == episode_rows)
        for start in starts:
            counts.append(count_window_overlap(len(positions), int(start), episode_rows, window_rows, stride, minimum_attacked))
    if not counts:
        return {"candidate_episode_starts": 0, "sampled_starts": 0, "windows_per_episode": qs(np.array([], dtype=float))}
    rng = np.random.default_rng(seed)
    chosen = rng.choice(np.asarray(counts), size=min(50_000, len(counts)), replace=False)
    evaluable = chosen[chosen > 0]
    return {
        "candidate_episode_starts": len(counts),
        "sampled_starts": len(chosen),
        "windows_per_episode": {**qs(chosen.astype(float)), "min": int(chosen.min()), "max": int(chosen.max()), "mean": float(chosen.mean())},
        "windows_per_evaluable_episode": {**qs(evaluable.astype(float)), "min": int(evaluable.min()), "max": int(evaluable.max()), "mean": float(evaluable.mean())} if len(evaluable) else None,
    }


def capacity_by_split_band(df: pd.DataFrame, mask: np.ndarray, speed_label: np.ndarray, maneuver: np.ndarray) -> dict[str, object]:
    result: dict[str, object] = {}
    for split in ("train", "val", "test"):
        split_mask = df["split"].eq(split).to_numpy() & mask
        bands: dict[str, object] = {}
        for band in ("0_50", "50_100", "100_200", "200_plus"):
            selected = split_mask & (speed_label == band)
            bands[band] = {
                "rows": int(selected.sum()),
                "segments": int(df.loc[selected, ["icao24", "segment_id"]].drop_duplicates().shape[0]),
                "aircraft": int(df.loc[selected, "icao24"].nunique()),
            }
        maneuver_counts = pd.Series(maneuver[split_mask]).value_counts().sort_index()
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


def oracle_boundary_recall(lat: np.ndarray, lon: np.ndarray, prev_lat: np.ndarray, prev_lon: np.ndarray, expected_north: np.ndarray, expected_east: np.ndarray, threshold: np.ndarray, valid: np.ndarray, size: int, seed: int) -> dict[str, object]:
    """In-memory abrupt horizontal-shift trial for a residual-threshold oracle."""
    rng = np.random.default_rng(seed)
    available = np.flatnonzero(valid)
    if len(available) == 0:
        return {"trial_rows": 0, "tiers": {}}
    selected = rng.choice(available, size=min(size, len(available)), replace=False)
    tiers = {"subtle": 500.0, "moderate": 2500.0, "blatant": 5500.0, "gross_positive_control": 11000.0}
    output: dict[str, object] = {}
    bearings = rng.uniform(0.0, 2.0 * np.pi, size=len(selected))
    local_lat = lat[selected]
    for name, magnitude in tiers.items():
        north_shift = magnitude * np.cos(bearings)
        east_shift = magnitude * np.sin(bearings)
        modified_north = (local_lat - prev_lat[selected]) * 111_320.0 + north_shift
        modified_east = (lon[selected] - prev_lon[selected]) * 111_320.0 * np.cos(np.deg2rad((local_lat + prev_lat[selected]) / 2.0)) + east_shift
        modified_residual = np.hypot(modified_north - expected_north[selected], modified_east - expected_east[selected])
        output[name] = {"horizontal_shift_meters": magnitude, "recall": float((modified_residual >= threshold[selected]).mean())}
    return {"trial_rows": int(len(selected)), "detector": "speed_band_p95_horizontal_residual", "abrupt_onset": True, "tiers": output}


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
    speed_threshold = {band: float(np.quantile(horizontal_residual[pair & (speed_label == band)], 0.95)) for band, _, _ in SPEED_BANDS}
    threshold = np.array([speed_threshold.get(str(label), np.inf) for label in speed_label], dtype=float)

    vertical_band = band_labels(np.abs(vertrate), VERTICAL_BANDS)
    baro_residual = np.abs((baro - previous_baro) - vertrate * dt)
    geo_residual = np.abs((geo - previous_geo) - vertrate * dt)
    altitude_valid = pair & np.isfinite(previous_baro) & np.isfinite(previous_geo)
    altitude = {
        "baroaltitude": residual_summary(baro_residual, altitude_valid, vertical_band, dt_label),
        "geoaltitude": residual_summary(geo_residual, altitude_valid, vertical_band, dt_label),
    }
    geo_threshold = float(np.quantile(geo_residual[altitude_valid], 0.999))
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

    def count(mask: np.ndarray) -> dict[str, int]:
        return {"rows": int(mask.sum()), "segments": int(df.loc[mask, ["icao24", "segment_id"]].drop_duplicates().shape[0]), "aircraft": int(df.loc[mask, "icao24"].nunique())}

    episode_distribution = {
        "replay_120_seconds_nominal": window_episode_distribution(df, replay_eligible, args.episode_rows, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed),
        "freeze_duration_rows": {
            "90_seconds": window_episode_distribution(df, eligibility, 9, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed),
            "120_seconds": window_episode_distribution(df, eligibility, 12, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed),
            "180_seconds": window_episode_distribution(df, eligibility, 18, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed),
            "300_seconds": window_episode_distribution(df, eligibility, 30, args.window_rows, args.window_stride_rows, args.minimum_attacked_rows, args.seed),
        },
    }

    report = {
        "report_version": 2,
        "read_only": True,
        "input": str(args.input).replace("\\", "/"),
        "split_file": str(args.splits).replace("\\", "/"),
        "parameters": {"replay_delay_seconds": args.replay_delay_seconds, "replay_tolerance_seconds": args.replay_tolerance_seconds, "window_rows": args.window_rows, "window_stride_rows": args.window_stride_rows, "minimum_attacked_rows": args.minimum_attacked_rows, "effect_gate": "partial replay: any speed/heading/vertical-rate change plus speed-band p95 hypothetical partial-field residual in >=3 consecutive rows"},
        "split_aircraft_coverage": split_coverage,
        "horizontal_residual_meters_by_dt_then_speed_band": residual_by_dt_speed,
        "speed_band_p95_threshold_meters": speed_threshold,
        "altitude_residual_meters_by_vertical_rate_then_dt": altitude,
        "geoaltitude_glitch_screen": {"rule": "absolute(altitude_change - vertical_rate*dt) > global q99.9", "threshold_meters": geo_threshold, "rows": int(geo_glitch.sum())},
        "replay": {
            "eligibility_only": count(replay_eligible),
            "partial_field_ungated_pair": count(replay_pair),
            "partial_field_full_effect_gate": count(partial_gated),
            "full_field": {"reporting": "ungated eligibility and boundary-stratified results only; no interior residual gate is scientifically valid", "eligibility_only": count(replay_eligible)},
            "capacity_after_gate_by_split_speed_band_replay_subtype": {
                "partial_field_ungated": {"rows": capacity_by_split_band(df, replay_pair, speed_label, maneuver), "episode_starts_120_seconds": episode_start_capacity(df, replay_eligible, None, speed_label, args.episode_rows)},
                "partial_field_gated": {"rows": capacity_by_split_band(df, partial_gated, speed_label, maneuver), "episode_starts_120_seconds": episode_start_capacity(df, replay_eligible, partial_gated, speed_label, args.episode_rows)},
                "full_field_eligibility_only": {"rows": capacity_by_split_band(df, replay_eligible & pair, speed_label, maneuver), "episode_starts_120_seconds": episode_start_capacity(df, replay_eligible, None, speed_label, args.episode_rows)},
            },
        },
        "windows_per_episode": episode_distribution,
        "oracle_boundary_trial": oracle_boundary_recall(lat, lon, previous_lat, previous_lon, expected_north, expected_east, threshold, pair, args.oracle_trial_size, args.seed),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=native) + "\n", encoding="utf-8")
    print(f"Wrote read-only calibration report: {args.output}")
    print(f"Replay eligible={report['replay']['eligibility_only']['rows']}; partial-field gated={report['replay']['partial_field_full_effect_gate']['rows']}")
    print(f"Geo glitch threshold={geo_threshold:.3f} m; rows={int(geo_glitch.sum())}")


if __name__ == "__main__":
    main()
