
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")
TIME_COL = "time"
AIRCRAFT_COL = "icao24"

files = sorted(RAW_DIR.glob("*.csv"))

if not files:
    raise FileNotFoundError("No CSV files found in data/raw")

for file in files:
    print(f"\n{'=' * 60}")
    print("File:", file.name)

    df = pd.read_csv(
        file,
        usecols=lambda c: c.strip() in {TIME_COL, AIRCRAFT_COL}
    )
    df.columns = df.columns.str.strip()

    df[TIME_COL] = pd.to_numeric(df[TIME_COL], errors="coerce")
    df = df.dropna(subset=[TIME_COL, AIRCRAFT_COL])

    print("Rows:", len(df))
    print("Unique aircraft:", df[AIRCRAFT_COL].nunique())

    print(
        "UTC time range:",
        pd.to_datetime(
            [df[TIME_COL].min(), df[TIME_COL].max()],
            unit="s",
            utc=True
        ).tolist()
    )

    # Sort within aircraft before calculating time gaps.
    df = df.sort_values([AIRCRAFT_COL, TIME_COL])

    gaps = (
        df.groupby(AIRCRAFT_COL, sort=False)[TIME_COL]
        .diff()
        .dropna()
    )

    if not gaps.empty:
        print("\nWithin-aircraft time gaps (seconds):")
        print(gaps.describe(percentiles=[0.5, 0.9, 0.95, 0.99]))

        print("Non-positive gaps:", int((gaps <= 0).sum()))
        print("Gaps > 30 seconds:", int((gaps > 30).sum()))

print("\nTemporal audit complete.")