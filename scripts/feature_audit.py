
from pathlib import Path
import pandas as pd
import numpy as np

RAW_DIR = Path("data/raw")
OUT_DIR = Path("results")
OUT_DIR.mkdir(exist_ok=True)

numeric_cols = [
    "lat", "lon", "velocity", "heading",
    "vertrate", "baroaltitude", "geoaltitude"
]

totals = {}
suspicious = {}
value_ranges = {}

for path in sorted(RAW_DIR.glob("*.csv")):
    print(f"\nAuditing {path.name}")

    totals[path.name] = {"rows": 0}
    suspicious[path.name] = {
        "invalid_lat": 0,
        "invalid_lon": 0,
        "negative_velocity": 0,
        "invalid_heading": 0,
        "extreme_vertical_rate_abs_gt_50": 0,
        "baro_alt_below_minus_1000": 0,
        "baro_alt_above_20000": 0,
        "geo_alt_below_minus_1000": 0,
        "geo_alt_above_20000": 0,
    }

    value_ranges[path.name] = {
        c: {"min": np.inf, "max": -np.inf, "missing": 0}
        for c in numeric_cols
    }

    for chunk in pd.read_csv(path, chunksize=200_000):
        chunk.columns = chunk.columns.str.strip()
        totals[path.name]["rows"] += len(chunk)

        for col in numeric_cols:
            if col not in chunk.columns:
                continue

            s = pd.to_numeric(chunk[col], errors="coerce")
            stats = value_ranges[path.name][col]
            stats["missing"] += int(s.isna().sum())

            if s.notna().any():
                stats["min"] = min(stats["min"], s.min())
                stats["max"] = max(stats["max"], s.max())

        lat = pd.to_numeric(chunk["lat"], errors="coerce")
        lon = pd.to_numeric(chunk["lon"], errors="coerce")
        vel = pd.to_numeric(chunk["velocity"], errors="coerce")
        hdg = pd.to_numeric(chunk["heading"], errors="coerce")
        vr = pd.to_numeric(chunk["vertrate"], errors="coerce")
        ba = pd.to_numeric(chunk["baroaltitude"], errors="coerce")
        ga = pd.to_numeric(chunk["geoaltitude"], errors="coerce")

        checks = {
            "invalid_lat": lat.notna() & ~lat.between(-90, 90),
            "invalid_lon": lon.notna() & ~lon.between(-180, 180),
            "negative_velocity": vel.notna() & (vel < 0),
            "invalid_heading": hdg.notna() & ~hdg.between(0, 360),
            "extreme_vertical_rate_abs_gt_50": vr.notna() & (vr.abs() > 50),
            "baro_alt_below_minus_1000": ba.notna() & (ba < -1000),
            "baro_alt_above_20000": ba.notna() & (ba > 20000),
            "geo_alt_below_minus_1000": ga.notna() & (ga < -1000),
            "geo_alt_above_20000": ga.notna() & (ga > 20000),
        }

        for name, mask in checks.items():
            suspicious[path.name][name] += int(mask.sum())

    print("Rows:", f"{totals[path.name]['rows']:,}")
    print("Suspicious-value counts:")
    for name, count in suspicious[path.name].items():
        print(f"  {name}: {count:,}")

    print("Full-file feature ranges and missingness:")
    for col, stats in value_ranges[path.name].items():
        lo = stats["min"]
        hi = stats["max"]
        if lo == np.inf:
            lo = hi = None

        missing_pct = 100 * stats["missing"] / totals[path.name]["rows"]
        print(
            f"  {col}: min={lo}, max={hi}, "
            f"missing={missing_pct:.2f}%"
        )

# Save machine-readable reports.
pd.DataFrame.from_dict(suspicious, orient="index").to_csv(
    OUT_DIR / "suspicious_values.csv"
)

range_rows = []
for filename, columns in value_ranges.items():
    for col, stats in columns.items():
        n = totals[filename]["rows"]
        range_rows.append({
            "file": filename,
            "column": col,
            "min": None if stats["min"] == np.inf else stats["min"],
            "max": None if stats["max"] == -np.inf else stats["max"],
            "missing_count": stats["missing"],
            "missing_percent": 100 * stats["missing"] / n,
        })

pd.DataFrame(range_rows).to_csv(
    OUT_DIR / "full_feature_ranges.csv", index=False
)

print("\nSaved:")
print("  results/suspicious_values.csv")
print("  results/full_feature_ranges.csv")