"""Build a cleaned OpenSky state-vector table without touching baseline data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


FEATURES = ["lat", "lon", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude"]
USECOLS = ["time", "icao24", "onground", *FEATURES, "lastcontact"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a cleaned OpenSky state-vector table.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/reproductions/phase0/processed"))
    parser.add_argument("--filename", default="opensky_clean_v1_reproduced.parquet")
    parser.add_argument("--segment-gap-seconds", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = sorted(args.raw_dir.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"No CSV files found in {args.raw_dir}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output = args.out_dir / args.filename
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output}")

    frames = []
    for path in paths:
        print("Reading:", path.name, flush=True)
        frame = pd.read_csv(path, usecols=USECOLS)
        frame.columns = frame.columns.str.strip()
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df = df.dropna(subset=["time", "icao24"]).copy()
    for col in FEATURES + ["lastcontact"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values(["icao24", "time"]).reset_index(drop=True)
    repeated = int(df.duplicated(["icao24", "time"], keep=False).sum())
    for col in FEATURES:
        df[f"{col}_missing"] = df[col].isna().astype("int8")
    angle = np.deg2rad(df["heading"])
    df["heading_sin"] = np.sin(angle)
    df["heading_cos"] = np.cos(angle)
    df["contact_lag_seconds"] = df["time"] - df["lastcontact"]
    df["contact_lag_missing"] = df["contact_lag_seconds"].isna().astype("int8")
    gap = df.groupby("icao24", sort=False)["time"].diff()
    df["segment_id"] = (gap.isna() | (gap > args.segment_gap_seconds)).groupby(df["icao24"], sort=False).cumsum().astype("int32")
    df.to_parquet(output, index=False)

    manifest = {
        "dataset_version": "phase0_cleaned_reproduction",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "source": "decoded OpenSky state vectors, not raw 112-bit ADS-B messages",
        "raw_inputs": [{"path": str(path), "bytes": path.stat().st_size} for path in paths],
        "segment_gap_seconds": args.segment_gap_seconds,
        "rows": int(len(df)),
        "aircraft": int(df["icao24"].nunique()),
        "segments": int(df[["icao24", "segment_id"]].drop_duplicates().shape[0]),
        "repeated_aircraft_timestamp_rows": repeated,
        "missingness": {col: int(df[col].isna().sum()) for col in FEATURES},
    }
    for name in ("config.json", "manifest.json"):
        (args.out_dir / name).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Saved:", output)
    print("Rows:", f"{manifest['rows']:,}")
    print("Aircraft:", f"{manifest['aircraft']:,}")
    print("Segments:", f"{manifest['segments']:,}")
    print("Rows involved in repeated aircraft/timestamp pairs:", repeated)


if __name__ == "__main__":
    main()
