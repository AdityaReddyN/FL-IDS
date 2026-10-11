
from pathlib import Path
import pandas as pd
import numpy as np

RAW_DIR = Path("data/raw")
OUT_DIR = Path("results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

files = sorted(RAW_DIR.glob("*.csv"))

if len(files) < 2:
    raise FileNotFoundError(
        f"Expected at least 2 CSV files in {RAW_DIR.resolve()}, "
        f"but found {len(files)}."
    )

print("Files found:")
for file in files:
    print(f"  {file.name} ({file.stat().st_size / 1024**2:.2f} MB)")

# Read one file at a time to keep memory use manageable.
frames = []

for file in files:
    print(f"\nReading {file.name} ...")
    df = pd.read_csv(file, low_memory=False)

    # Standardize header whitespace, not the actual data.
    df.columns = df.columns.str.strip()

    print("Shape:", df.shape)
    print("Columns:", df.columns.tolist())

    frames.append(df)

data = pd.concat(frames, ignore_index=True)
print("\nCombined shape:", data.shape)

# Adapt these aliases if your CSV uses different column names.
aliases = {
    "time": ["time", "timestamp"],
    "icao24": ["icao24", "icao_24"],
    "lat": ["lat", "latitude"],
    "lon": ["lon", "longitude"],
    "velocity": ["velocity", "groundspeed"],
    "heading": ["heading", "true_track"],
    "vertrate": ["vertrate", "vertical_rate"],
    "baroaltitude": ["baroaltitude", "baro_altitude"],
    "geoaltitude": ["geoaltitude", "geo_altitude"],
}

lower_to_actual = {c.lower(): c for c in data.columns}
rename = {}

for canonical, candidates in aliases.items():
    for candidate in candidates:
        if candidate in lower_to_actual:
            rename[lower_to_actual[candidate]] = canonical
            break

data = data.rename(columns=rename)

required = ["time", "icao24", "lat", "lon"]
missing = [c for c in required if c not in data.columns]

if missing:
    print("\nRequired columns not found:", missing)
    print("Check the printed column names and adapt the aliases.")
    raise SystemExit(1)

# Save original row count and inspect duplicates before dropping anything.
print("\nExact duplicate rows:", data.duplicated().sum())

# Convert numeric columns, preserving missing values as NaN.
numeric_cols = [
    c for c in [
        "time", "lat", "lon", "velocity", "heading",
        "vertrate", "baroaltitude", "geoaltitude"
    ]
    if c in data.columns
]

for col in numeric_cols:
    data[col] = pd.to_numeric(data[col], errors="coerce")

print("\nMissing-value rate:")
print(data.isna().mean().sort_values(ascending=False).to_string())

print("\nUnique aircraft:", data["icao24"].nunique(dropna=True))
print("Rows per aircraft — descriptive statistics:")
print(data.groupby("icao24", dropna=True).size().describe())

print("\nCoordinate validity:")
print("Latitude outside [-90, 90]:",
      ((data["lat"] < -90) | (data["lat"] > 90)).sum())
print("Longitude outside [-180, 180]:",
      ((data["lon"] < -180) | (data["lon"] > 180)).sum())

# OpenSky state-vector timestamps are normally Unix seconds.
valid_time = data["time"].dropna()
if not valid_time.empty:
    print("\nTimestamp range (UTC):")
    print(pd.to_datetime(valid_time.min(), unit="s", utc=True))
    print(pd.to_datetime(valid_time.max(), unit="s", utc=True))

# Save a reportable audit summary.
summary = {
    "rows": len(data),
    "columns": len(data.columns),
    "unique_aircraft": data["icao24"].nunique(dropna=True),
    "exact_duplicate_rows": int(data.duplicated().sum()),
    "missing_time": int(data["time"].isna().sum()),
    "missing_icao24": int(data["icao24"].isna().sum()),
    "missing_lat": int(data["lat"].isna().sum()),
    "missing_lon": int(data["lon"].isna().sum()),
}

pd.Series(summary, name="value").to_csv(
    OUT_DIR / "audit_summary.csv"
)

data.isna().mean().rename("missing_fraction").to_csv(
    OUT_DIR / "missingness.csv"
)

print("\nAudit finished. Reports saved in results/.")