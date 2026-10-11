
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")

cols = [
    "time", "icao24", "lat", "lon", "velocity",
    "heading", "vertrate", "onground",
    "baroaltitude", "geoaltitude"
]

for path in sorted(RAW_DIR.glob("*.csv")):
    print(f"\n{'=' * 70}")
    print(path.name)

    # Read in chunks so the full files do not have to stay in memory.
    extreme_rows = []

    for chunk in pd.read_csv(path, usecols=cols, chunksize=200_000):
        chunk["vertrate"] = pd.to_numeric(
            chunk["vertrate"], errors="coerce"
        )

        matches = chunk[chunk["vertrate"].abs() > 50]
        if not matches.empty:
            extreme_rows.append(matches)

    if not extreme_rows:
        print("No extreme vertical-rate records found.")
        continue

    extremes = pd.concat(extreme_rows, ignore_index=True)
    print("Extreme records:", len(extremes))

    # Show up to five examples.
    print("\nRepresentative extreme records:")
    print(extremes.head(5).to_string(index=False))

    # Inspect their neighbours in the original CSV.
    aircraft_ids = extremes["icao24"].dropna().unique()[:3]
    sample_times = extremes[
        extremes["icao24"].isin(aircraft_ids)
    ]["time"].dropna().tolist()[:3]

    if not sample_times:
        continue

    targets = extremes[
        extremes["time"].isin(sample_times)
    ][["icao24", "time"]].drop_duplicates()

    for _, target in targets.iterrows():
        print(
            f"\nNeighbourhood: aircraft={target['icao24']}, "
            f"time={target['time']}"
        )

        before = target["time"] - 30
        after = target["time"] + 30

        # Only read relevant columns from the source file.
        neighbours = []

        for chunk in pd.read_csv(
            path, usecols=cols, chunksize=200_000
        ):
            chunk["time"] = pd.to_numeric(
                chunk["time"], errors="coerce"
            )

            mask = (
                (chunk["icao24"] == target["icao24"])
                & chunk["time"].between(before, after)
            )

            if mask.any():
                neighbours.append(chunk.loc[mask])

        if neighbours:
            view = pd.concat(neighbours, ignore_index=True)
            view = view.sort_values("time")
            print(view.to_string(index=False))

print("\nInspection complete.")