"""Write simple before/after SVG track plots for one episode per family."""
from __future__ import annotations

import argparse
import html
from pathlib import Path

import numpy as np
import pandas as pd


def _polyline_points(lat, lon, width: int, height: int, padding: int, bounds) -> str:
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    valid = np.isfinite(lat) & np.isfinite(lon)
    if not valid.any():
        return ""
    lat, lon = lat[valid], lon[valid]
    lat_min, lat_max, lon_min, lon_max = bounds
    x_scale = max(lon_max - lon_min, 1e-9)
    y_scale = max(lat_max - lat_min, 1e-9)
    points = []
    for x, y in zip(lon, lat):
        sx = padding + (x - lon_min) * (width - 2 * padding) / x_scale
        sy = height - padding - (y - lat_min) * (height - 2 * padding) / y_scale
        points.append(f"{sx:.2f},{sy:.2f}")
    return " ".join(points)


def render_track_svg(rows: pd.DataFrame, family: str, episode_id: int) -> str:
    """Render original and modified coordinates for one episode's segment."""
    width, height, padding = 900, 600, 48
    all_lat = np.concatenate((rows.orig_lat.to_numpy(dtype=float, na_value=np.nan), rows.mod_lat.to_numpy(dtype=float, na_value=np.nan)))
    all_lon = np.concatenate((rows.orig_lon.to_numpy(dtype=float, na_value=np.nan), rows.mod_lon.to_numpy(dtype=float, na_value=np.nan)))
    valid = np.isfinite(all_lat) & np.isfinite(all_lon)
    bounds = (float(np.min(all_lat[valid])), float(np.max(all_lat[valid])), float(np.min(all_lon[valid])), float(np.max(all_lon[valid]))) if valid.any() else (0.0, 1.0, 0.0, 1.0)
    before = _polyline_points(rows.orig_lat, rows.orig_lon, width, height, padding, bounds)
    after = _polyline_points(rows.mod_lat, rows.mod_lon, width, height, padding, bounds)
    safe_family = html.escape(str(family))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<text x="{padding}" y="28" font-family="sans-serif" font-size="18">{safe_family}, episode {int(episode_id)} — decoded state-vector track</text>
<polyline points="{before}" fill="none" stroke="#3569a8" stroke-width="2"/>
<polyline points="{after}" fill="none" stroke="#d04a3a" stroke-width="2"/>
<line x1="{padding}" y1="{height-padding+12}" x2="{padding+24}" y2="{height-padding+12}" stroke="#3569a8" stroke-width="3"/><text x="{padding+30}" y="{height-padding+17}" font-family="sans-serif" font-size="13">original</text>
<line x1="{padding+115}" y1="{height-padding+12}" x2="{padding+139}" y2="{height-padding+12}" stroke="#d04a3a" stroke-width="3"/><text x="{padding+145}" y="{height-padding+17}" font-family="sans-serif" font-size="13">modified</text>
</svg>\n'''


def write_family_plots(dataset_dir: str | Path, output_dir: str | Path | None = None) -> list[Path]:
    dataset_dir = Path(dataset_dir)
    target = Path(output_dir) if output_dir is not None else dataset_dir / "plots"
    target.mkdir(parents=True, exist_ok=True)
    episodes = pd.read_parquet(dataset_dir / "episodes.parquet")
    rows = pd.read_parquet(dataset_dir / "attacked_rows.parquet")
    written = []
    accepted = episodes.loc[episodes.accepted].sort_values(["attack_family", "episode_id"], kind="mergesort")
    for family, family_episodes in accepted.groupby("attack_family", sort=True):
        episode = family_episodes.iloc[0]
        group = rows.loc[
            (rows.icao24 == episode.icao24)
            & (rows.segment_id == episode.segment_id)
        ].sort_values("segment_row_offset", kind="mergesort")
        path = target / f"{family}.svg"
        path.write_text(render_track_svg(group, family, int(episode.episode_id)), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    paths = write_family_plots(args.dataset_dir, args.out_dir)
    print(f"Wrote {len(paths)} SVG sanity plots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
