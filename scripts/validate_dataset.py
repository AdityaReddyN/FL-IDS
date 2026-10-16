"""Report basic integrity and coverage statistics for a cleaned table."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a cleaned OpenSky state-vector table.")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    df = pd.read_parquet(args.input)
    features = ["lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude"]
    lengths = df.groupby(["icao24", "segment_id"]).size()
    span = pd.to_datetime(df["time"], unit="s", utc=True).agg(["min", "max"])
    print("Input:", args.input)
    print("Rows:", f"{len(df):,}")
    print("Columns:", len(df.columns))
    print("Unique aircraft:", f"{df['icao24'].nunique():,}")
    print("Unique trajectory segments:", f"{df[['icao24', 'segment_id']].drop_duplicates().shape[0]:,}")
    print("Repeated aircraft/timestamp rows:", int(df.duplicated(["icao24", "time"]).sum()))
    print("Missing values in core features:")
    print(df[features].isna().sum().to_string())
    print("Segment length distribution:")
    print(lengths.describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.99]).to_string())
    print("Time range:", span["min"], "to", span["max"])
    print(f"Latitude range: [{df['lat'].min(skipna=True):.6f}, {df['lat'].max(skipna=True):.6f}]")
    print(f"Longitude range: [{df['lon'].min(skipna=True):.6f}, {df['lon'].max(skipna=True):.6f}]")


if __name__ == "__main__":
    main()
