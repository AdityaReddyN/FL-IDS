
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")
cols = [
    "time", "icao24", "lat", "lon", "velocity",
    "heading", "vertrate", "onground",
    "baroaltitude", "geoaltitude",
    "lastposupdate", "lastcontact"
]

for path in sorted(RAW_DIR.glob("*.csv")):
    print(f"\n{'=' * 60}\n{path.name}")
    total = 0
    counters = {
        "missing_both_position": 0,
        "missing_velocity": 0,
        "missing_altitude_both": 0,
        "ground_missing_position": 0,
        "stale_contact_over_15s": 0,
        "contact_after_state_time": 0,
    }

    for df in pd.read_csv(path, usecols=cols, chunksize=200_000):
        df.columns = df.columns.str.strip()
        total += len(df)

        for c in [
            "time", "lat", "lon", "velocity", "baroaltitude",
            "geoaltitude", "lastcontact", "lastposupdate"
        ]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        counters["missing_both_position"] += int(
            (df["lat"].isna() & df["lon"].isna()).sum()
        )
        counters["missing_velocity"] += int(df["velocity"].isna().sum())
        counters["missing_altitude_both"] += int(
            (df["baroaltitude"].isna() & df["geoaltitude"].isna()).sum()
        )
        counters["ground_missing_position"] += int(
            (
                df["onground"].eq(True)
                & (df["lat"].isna() | df["lon"].isna())
            ).sum()
        )

        # Use only rows where timestamps are available.
        valid_contact = df["time"].notna() & df["lastcontact"].notna()
        counters["stale_contact_over_15s"] += int(
            (
                valid_contact
                & ((df["time"] - df["lastcontact"]) > 15)
            ).sum()
        )
        counters["contact_after_state_time"] += int(
            (
                valid_contact
                & (df["lastcontact"] > df["time"])
            ).sum()
        )

    print("Rows:", f"{total:,}")
    for name, count in counters.items():
        print(f"{name}: {count:,} ({100 * count / total:.2f}%)")

print("\nData-quality audit complete.")