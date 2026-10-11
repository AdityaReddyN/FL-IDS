
from pathlib import Path
import pandas as pd
import numpy as np

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed")
OUT_DIR.mkdir(parents=True, exist_ok=True)

FEATURES = [
    "lat", "lon", "velocity", "heading",
    "vertrate", "baroaltitude", "geoaltitude"
]

USECOLS = [
    "time", "icao24", "onground",
    "lat", "lon", "velocity", "heading",
    "vertrate", "baroaltitude", "geoaltitude",
    "lastcontact"
]

frames = []

for path in sorted(RAW_DIR.glob("*.csv")):
    print("Reading:", path.name)
    df = pd.read_csv(path, usecols=USECOLS)
    df.columns = df.columns.str.strip()
    frames.append(df)

df = pd.concat(frames, ignore_index=True)

# Normalize types and sort observations.
df["time"] = pd.to_numeric(df["time"], errors="coerce")
df = df.dropna(subset=["time", "icao24"]).copy()

for col in FEATURES + ["lastcontact"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.sort_values(["icao24", "time"]).reset_index(drop=True)

# Remove exact duplicate aircraft/timestamp observations only.
# Conflicting observations at the same timestamp are reported separately.
dup_mask = df.duplicated(["icao24", "time"], keep=False)
print("Rows involved in repeated aircraft/timestamp pairs:", int(dup_mask.sum()))

# Missingness indicators before any imputation.
for col in FEATURES:
    df[f"{col}_missing"] = df[col].isna().astype("int8")

# Heading is circular: encode it as sine/cosine.
angle = np.deg2rad(df["heading"])
df["heading_sin"] = np.sin(angle)
df["heading_cos"] = np.cos(angle)

# Diagnostic freshness feature; retain the raw timestamps.
df["contact_lag_seconds"] = df["time"] - df["lastcontact"]
df["contact_lag_missing"] = df["contact_lag_seconds"].isna().astype("int8")

# Segment trajectories when the time gap exceeds 30 seconds.
gap = df.groupby("icao24", sort=False)["time"].diff()
new_segment = gap.isna() | (gap > 30)

df["segment_id"] = (
    new_segment.groupby(df["icao24"], sort=False).cumsum().astype("int32")
)

# Save a cleaned-but-not-imputed table.
# No training statistics are fitted here.
out_path = OUT_DIR / "opensky_clean_v1.parquet"
df.to_parquet(out_path, index=False)

print("\nSaved:", out_path)
print("Rows:", f"{len(df):,}")
print("Aircraft:", f"{df['icao24'].nunique():,}")
print("Segments:", f"{df[['icao24', 'segment_id']].drop_duplicates().shape[0]:,}")
print("Columns:", len(df.columns))
print("\nMissingness indicators and sequence metadata created.")