
from pathlib import Path
import pandas as pd

path = Path("data/processed/opensky_clean_v1.parquet")
df = pd.read_parquet(path, columns=["icao24", "segment_id", "time"])

lengths = df.groupby(["icao24", "segment_id"]).size()

for seq_len in [20, 30, 40, 60]:
    eligible = lengths[lengths >= seq_len]
    windows = (eligible - seq_len + 1).sum()

    print(f"\nSequence length: {seq_len}")
    print(f"Eligible segments: {len(eligible):,}")
    print(f"Possible overlapping windows: {windows:,}")