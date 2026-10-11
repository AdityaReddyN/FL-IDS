
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")
FILES = sorted(RAW_DIR.glob("*.csv"))

if len(FILES) < 2:
    raise RuntimeError("Expected both hourly CSV files in data/raw")

parts = []

for path in FILES:
    df = pd.read_csv(
        path,
        usecols=lambda c: c.strip() in {"time", "icao24"}
    )
    df.columns = df.columns.str.strip()
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df = df.dropna(subset=["time", "icao24"])
    parts.append(df)
    print(f"Loaded {path.name}: {len(df):,} rows")

# Compare aircraft across hourly files.
aircraft_sets = [
    set(df["icao24"].unique()) for df in parts
]

print("\nAircraft overlap")
print("Hour 1 aircraft:", f"{len(aircraft_sets[0]):,}")
print("Hour 2 aircraft:", f"{len(aircraft_sets[1]):,}")
print("Aircraft in both:", f"{len(aircraft_sets[0] & aircraft_sets[1]):,}")

# Combine only the required columns.
df = pd.concat(parts, ignore_index=True)
df = df.sort_values(["icao24", "time"])

# Split sequences at gaps greater than 30 seconds.
df["gap"] = df.groupby("icao24")["time"].diff()
df["new_segment"] = df["gap"].isna() | (df["gap"] > 30)

df["segment"] = (
    df.groupby("icao24")["new_segment"].cumsum()
)

segments = df.groupby(["icao24", "segment"]).agg(
    rows=("time", "size"),
    start=("time", "min"),
    end=("time", "max")
)

print("\nTrajectory segments")
print("Total segments:", f"{len(segments):,}")
print("Segments with >= 10 observations:",
      f"{(segments['rows'] >= 10).sum():,}")
print("Segments with >= 30 observations:",
      f"{(segments['rows'] >= 30).sum():,}")
print("Segments with >= 60 observations:",
      f"{(segments['rows'] >= 60).sum():,}")

print("\nSegment length in observations:")
print(segments["rows"].describe(
    percentiles=[0.5, 0.75, 0.9, 0.95, 0.99]
))

Path("results").mkdir(exist_ok=True)
segments.to_csv("results/trajectory_segments.csv")

print("\nSaved results/trajectory_segments.csv")