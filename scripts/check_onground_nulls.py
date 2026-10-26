"""Read-only report of null ``onground`` counts per split on the cleaned table.

Run this yourself; it reads the immutable cleaned table and a split file and
writes one JSON report plus a short printed summary. It generates no attacks,
windows, or datasets and modifies nothing. Null ``onground`` rows are ineligible
for every attack family (D-038); this check quantifies how many such rows exist
per split before any generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.attacks.splits import (  # noqa: E402
    SPLIT_NAMES,
    load_split_aircraft,
    validate_splits,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/opensky_clean_v1.parquet"),
    )
    parser.add_argument(
        "--splits",
        type=Path,
        default=Path("data/sequences_v2/split_aircraft.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results/onground_nulls_v1/report.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Reading immutable cleaned table (onground, icao24 only)...", flush=True)
    df = pd.read_parquet(args.input, columns=["icao24", "onground"])

    splits = load_split_aircraft(args.splits)
    validate_splits(splits, df["icao24"].unique())
    split_series = df["icao24"].map(splits.assignments)
    if split_series.isna().any():
        missing = sorted(df.loc[split_series.isna(), "icao24"].unique().tolist())[:3]
        raise ValueError(f"aircraft missing from split file, e.g. {missing}")

    is_null = df["onground"].isna().to_numpy()
    per_split = {}
    for name in SPLIT_NAMES:
        in_split = (split_series == name).to_numpy()
        n_rows = int(in_split.sum())
        n_null = int((is_null & in_split).sum())
        per_split[name] = {
            "n_rows": n_rows,
            "n_null_onground": n_null,
            "null_share_pct": round(100.0 * n_null / n_rows, 6) if n_rows else None,
        }

    report = {
        "parameters": {"input": str(args.input), "splits": str(args.splits)},
        "rows_total": int(len(df)),
        "n_null_onground_total": int(is_null.sum()),
        "onground_dtype": str(df["onground"].dtype),
        "per_split": per_split,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    print(
        f"Rows={report['rows_total']:,}; "
        f"null onground total={report['n_null_onground_total']:,} "
        f"(dtype {report['onground_dtype']})"
    )
    for name in SPLIT_NAMES:
        entry = per_split[name]
        share = entry["null_share_pct"]
        print(
            f"  {name}: {entry['n_null_onground']:,} null "
            f"of {entry['n_rows']:,} ({share}%)"
        )
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
