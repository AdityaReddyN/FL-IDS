
from pathlib import Path
import pandas as pd

path = Path("data/processed/opensky_clean_v1.parquet")
df = pd.read_parquet(path)

print("Rows:", f"{len(df):,}")
print("Columns:", len(df.columns))
print("Unique aircraft:", f"{df['icao24'].nunique():,}")
print("Unique trajectory segments:",
      f"{df[['icao24', 'segment_id']].drop_duplicates().shape[0]:,}")

print("\nRepeated aircraft/timestamp rows:")
print(df.duplicated(["icao24", "time"]).sum())

print("\nMissing values in core features:")
features = [
    "lat", "lon", "velocity", "heading",
    "vertrate", "baroaltitude", "geoaltitude"
]
print(df[features].isna().sum())

print("\nSegment length distribution:")
lengths = df.groupby(["icao24", "segment_id"]).size()
print(lengths.describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.99]))

print("\nTime range:")
print(pd.to_datetime(df["time"], unit="s", utc=True).agg(["min", "max"]))