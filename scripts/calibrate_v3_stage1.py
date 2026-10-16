"""Read-only feasibility calibration for the proposed V3 Stage 1 configuration.

The script reads immutable inputs and writes no files. It reports 5-degree grid
coverage, density samples, current eligibility yields, kinematic residuals,
replay-change candidates, and geographic-altitude vertical-step outliers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


CORE = ["lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/opensky_clean_v1.parquet"))
    parser.add_argument("--splits", type=Path, default=Path("data/sequences_v2/split_aircraft.json"))
    parser.add_argument("--grid-degrees", type=float, default=5.0)
    parser.add_argument("--density-window-seconds", type=float, default=60.0)
    parser.add_argument("--max-contact-lag-seconds", type=float, default=30.0)
    parser.add_argument("--replay-delay-seconds", type=float, default=300.0)
    parser.add_argument("--replay-tolerance-seconds", type=float, default=5.0)
    parser.add_argument("--window-rows", type=int, default=30)
    parser.add_argument("--window-stride-rows", type=int, default=10)
    parser.add_argument("--speed-change-mps", type=float, default=1.0)
    parser.add_argument("--heading-change-degrees", type=float, default=1.0)
    parser.add_argument("--vertical-rate-change-mps", type=float, default=0.5)
    parser.add_argument("--grid-detail", action="store_true")
    parser.add_argument("--seed", type=int, default=42, help="Recorded for CLI consistency; unused because this diagnostic is deterministic.")
    return parser.parse_args()


def quantiles(values: np.ndarray, qs: list[float] = [0.5, 0.9, 0.95, 0.99]) -> dict[str, float]:
    if len(values) == 0:
        return {f"q{int(q * 100)}": float("nan") for q in qs}
    return {f"q{int(q * 100)}": float(np.quantile(values, q)) for q in qs}


def circular_difference_degrees(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.abs((a - b + 180.0) % 360.0 - 180.0)


def add_split(df: pd.DataFrame, split_path: Path) -> pd.DataFrame:
    split_ids = json.loads(split_path.read_text(encoding="utf-8"))
    mapping = {icao: split for split, aircraft in split_ids.items() for icao in aircraft}
    df["split"] = df["icao24"].astype(str).map(mapping)
    if df["split"].isna().any():
        raise ValueError("Some source rows are absent from split_aircraft.json")
    return df


def density_samples(df: pd.DataFrame, window_seconds: float) -> np.ndarray:
    """Count unique aircraft in fixed grid-cell/time windows without sampling bias."""
    buckets = np.floor(df["time"].to_numpy(dtype=float) / window_seconds).astype(np.int64)
    grouped = (
        df.assign(_density_bucket=buckets)
        .groupby(["grid_lat", "grid_lon", "_density_bucket"], dropna=True)["icao24"]
        .nunique()
    )
    return grouped.to_numpy(dtype=np.int32)


def replay_links(df: pd.DataFrame, base_eligible: np.ndarray, delay: float, tolerance: float) -> np.ndarray:
    """Return source-row positions for replay-eligible targets, -1 otherwise."""
    prior_position = np.full(len(df), -1, dtype=np.int64)
    groups = df.groupby(["icao24", "segment_id"], sort=False).indices
    times = df["time"].to_numpy(dtype=float)
    for indices in groups.values():
        indices = np.asarray(indices, dtype=np.int64)
        source_indices = indices[base_eligible[indices]]
        if len(source_indices) == 0:
            continue
        source_times = times[source_indices]
        target_indices = source_indices
        desired = times[target_indices] - delay
        right = np.searchsorted(source_times, desired, side="left")
        left = np.clip(right - 1, 0, len(source_times) - 1)
        right = np.clip(right, 0, len(source_times) - 1)
        choose_right = np.abs(source_times[right] - desired) < np.abs(source_times[left] - desired)
        selected = np.where(choose_right, right, left)
        differences = np.abs(source_times[selected] - desired)
        valid = (differences <= tolerance) & (source_times[selected] < times[target_indices])
        prior_position[target_indices[valid]] = source_indices[selected[valid]]
    return prior_position


def print_yield(df: pd.DataFrame, label: str, mask: np.ndarray) -> None:
    print(f"\n{label}")
    for split in ("train", "val", "test"):
        subset = df["split"].eq(split).to_numpy()
        total_rows = int(subset.sum())
        total_segments = int(df.loc[subset, ["icao24", "segment_id"]].drop_duplicates().shape[0])
        total_aircraft = int(df.loc[subset, "icao24"].nunique())
        selected = subset & mask
        rows = int(selected.sum())
        segments = int(df.loc[selected, ["icao24", "segment_id"]].drop_duplicates().shape[0])
        aircraft = int(df.loc[selected, "icao24"].nunique())
        print(
            f"{split}: rows={rows}/{total_rows} ({rows / total_rows:.2%}); "
            f"segments={segments}/{total_segments} ({segments / total_segments:.2%}); "
            f"aircraft={aircraft}/{total_aircraft} ({aircraft / total_aircraft:.2%})"
        )


def print_window_capacity(df: pd.DataFrame, label: str, mask: np.ndarray, window_rows: int, stride_rows: int) -> None:
    """Report an upper-bound count of windows entirely inside consecutive eligible rows.

    This is a feasibility figure only: it neither injects attacks nor accounts for
    per-type amplitude/detectability rejection, episode separation, or quotas.
    """
    print(f"\nWINDOW_CAPACITY_{label} window_rows={window_rows} stride_rows={stride_rows}")
    for split in ("train", "val", "test"):
        capacity = 0
        supporting_segments: set[tuple[str, int]] = set()
        supporting_aircraft: set[str] = set()
        for (icao24, segment_id), positions in df.groupby(["icao24", "segment_id"], sort=False).indices.items():
            positions = np.asarray(positions, dtype=np.int64)
            if df["split"].iat[positions[0]] != split:
                continue
            eligible = mask[positions]
            padded = np.r_[False, eligible, False].astype(np.int8)
            starts = np.flatnonzero(np.diff(padded) == 1)
            ends = np.flatnonzero(np.diff(padded) == -1)
            count = sum(max(0, 1 + (end - start - window_rows) // stride_rows) for start, end in zip(starts, ends))
            if count:
                capacity += count
                supporting_segments.add((str(icao24), int(segment_id)))
                supporting_aircraft.add(str(icao24))
        print(
            f"{split}: max_all_eligible_windows={capacity}; "
            f"supporting_segments={len(supporting_segments)}; supporting_aircraft={len(supporting_aircraft)}"
        )


def main() -> None:
    args = parse_args()
    columns = ["icao24", "segment_id", "time", "onground", "contact_lag_seconds", *CORE]
    print("Reading immutable cleaned table...", flush=True)
    df = pd.read_parquet(args.input, columns=columns).sort_values(["icao24", "segment_id", "time"]).reset_index(drop=True)
    df = add_split(df, args.splits)
    df["grid_lat"] = np.floor(df["lat"] / args.grid_degrees) * args.grid_degrees
    df["grid_lon"] = np.floor(df["lon"] / args.grid_degrees) * args.grid_degrees

    print("\nBOUNDING_BOX")
    print(f"lat=[{df.lat.min():.6f}, {df.lat.max():.6f}] lon=[{df.lon.min():.6f}, {df.lon.max():.6f}]")
    grid = df.groupby(["grid_lat", "grid_lon"], dropna=True).agg(rows=("icao24", "size"), aircraft=("icao24", "nunique")).reset_index()
    print(f"occupied_grid_cells={len(grid)}")
    if args.grid_detail:
        print("GRID_CELL_COUNTS grid_lat,grid_lon,rows,aircraft")
        for row in grid.sort_values(["grid_lat", "grid_lon"]).itertuples(index=False):
            print(f"{row.grid_lat:.1f},{row.grid_lon:.1f},{row.rows},{row.aircraft}")

    print("\nDENSITY_RHO")
    rho = density_samples(df.dropna(subset=["grid_lat", "grid_lon"]), args.density_window_seconds)
    print(
        f"window_seconds={args.density_window_seconds:g} samples={len(rho)} min={rho.min()} max={rho.max()} "
        f"q50={np.quantile(rho, .5):.2f} q90={np.quantile(rho, .9):.2f} q99={np.quantile(rho, .99):.2f}"
    )

    observed = df[CORE].notna().all(axis=1).to_numpy()
    lag = df["contact_lag_seconds"].to_numpy(dtype=float)
    airborne = ~df["onground"].fillna(False).astype(bool).to_numpy()
    not_stale = np.isfinite(lag) & (lag >= 0.0) & (lag <= args.max_contact_lag_seconds)
    base = airborne & not_stale & observed
    print_yield(df, "ELIGIBILITY_CURRENT_FULL_FIELD", base)
    print_window_capacity(df, "CURRENT_FULL_FIELD", base, args.window_rows, args.window_stride_rows)

    prior = replay_links(df, base, args.replay_delay_seconds, args.replay_tolerance_seconds)
    replay = prior >= 0
    print_yield(df, "ELIGIBILITY_REPLAY_WITH_300S_HISTORY", replay)
    print_window_capacity(df, "REPLAY_WITH_300S_HISTORY", replay, args.window_rows, args.window_stride_rows)

    velocity = df["velocity"].to_numpy(dtype=float)
    heading = df["heading"].to_numpy(dtype=float)
    vertrate = df["vertrate"].to_numpy(dtype=float)
    changed_speed = np.zeros(len(df), dtype=bool)
    changed_heading = np.zeros(len(df), dtype=bool)
    changed_vrate = np.zeros(len(df), dtype=bool)
    target_positions = np.flatnonzero(replay)
    source_positions = prior[target_positions]
    changed_speed[target_positions] = np.abs(velocity[target_positions] - velocity[source_positions]) >= args.speed_change_mps
    changed_heading[target_positions] = circular_difference_degrees(heading[target_positions], heading[source_positions]) >= args.heading_change_degrees
    changed_vrate[target_positions] = np.abs(vertrate[target_positions] - vertrate[source_positions]) >= args.vertical_rate_change_mps
    measurable = changed_speed | changed_heading | changed_vrate
    print("\nREPLAY_CANDIDATE_CHANGE")
    print(f"candidates={int(replay.sum())} speed_change={int(changed_speed.sum())} heading_change={int(changed_heading.sum())} vertical_rate_change={int(changed_vrate.sum())} any_measurable={int(measurable.sum())}")

    groups = df.groupby(["icao24", "segment_id"], sort=False)
    prev_lat = groups["lat"].shift().to_numpy(dtype=float)
    prev_lon = groups["lon"].shift().to_numpy(dtype=float)
    prev_time = groups["time"].shift().to_numpy(dtype=float)
    prev_base = pd.Series(base).groupby([df["icao24"], df["segment_id"]], sort=False).shift().fillna(False).to_numpy(dtype=bool)
    dt = df["time"].to_numpy(dtype=float) - prev_time
    kin = base & prev_base & np.isfinite(prev_lat) & np.isfinite(prev_lon) & np.isfinite(velocity) & np.isfinite(heading) & (dt > 0) & (dt <= 30)
    north = (df["lat"].to_numpy(dtype=float) - prev_lat) * 111_320.0
    east = (df["lon"].to_numpy(dtype=float) - prev_lon) * 111_320.0 * np.cos(np.deg2rad((df["lat"].to_numpy(dtype=float) + prev_lat) / 2.0))
    expected = velocity * dt
    expected_north = expected * np.cos(np.deg2rad(heading))
    expected_east = expected * np.sin(np.deg2rad(heading))
    residual = np.hypot(north - expected_north, east - expected_east)
    print("\nKINEMATIC_RESIDUAL_METERS position_step_vs_velocity_heading")
    for name, lower, upper in (("0_50", 0, 50), ("50_100", 50, 100), ("100_200", 100, 200), ("200_plus", 200, np.inf)):
        mask = kin & (velocity >= lower) & (velocity < upper)
        values = residual[mask]
        q = quantiles(values)
        print(f"speed_band={name} n={len(values)} q50={q['q50']:.2f} q90={q['q90']:.2f} q95={q['q95']:.2f} q99={q['q99']:.2f}")

    geo = df["geoaltitude"].to_numpy(dtype=float)
    prev_geo = groups["geoaltitude"].shift().to_numpy(dtype=float)
    vertical = np.abs((geo - prev_geo) / dt)
    geo_valid = kin & np.isfinite(geo) & np.isfinite(prev_geo)
    geo_values = vertical[geo_valid]
    print("\nGEOALTITUDE_VERTICAL_STEP_OUTLIERS_MPS")
    print(f"n={len(geo_values)} q50={np.quantile(geo_values,.5):.3f} q90={np.quantile(geo_values,.9):.3f} q99={np.quantile(geo_values,.99):.3f} q999={np.quantile(geo_values,.999):.3f} max={geo_values.max():.3f} gt100={int((geo_values > 100).sum())} gt200={int((geo_values > 200).sum())}")


if __name__ == "__main__":
    main()
