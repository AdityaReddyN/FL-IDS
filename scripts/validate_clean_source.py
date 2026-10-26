"""Validate a cleaned HDD source directory against the opensky_clean_v1 contract.

Human-run, read-only. Reads the clean parts one at a time (memory-bounded) and
writes a JSON pass/fail report: schema equality, natural-key uniqueness, sorted
order, within-segment 10 s cadence, split coverage/disjointness, and a
rows/aircraft/segments/missingness table against the old 2-hour source.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.data.clean import CLEAN_COLUMNS, FEATURES  # noqa: E402
from flids.attacks.splits import load_split_aircraft, validate_splits  # noqa: E402

# Expected pandas dtype family per column (onground may be bool or nullable boolean).
_EXPECTED_DTYPE = {
    "time": "int64", "icao24": "object/string",
    **{name: "float64" for name in FEATURES},
    "onground": "bool/boolean", "lastcontact": "float64",
    **{f"{name}_missing": "int8" for name in FEATURES},
    "heading_sin": "float64", "heading_cos": "float64",
    "contact_lag_seconds": "float64", "contact_lag_missing": "int8",
    "segment_id": "int32",
}


def _dtype_ok(column: str, dtype) -> bool:
    name = str(dtype)
    expected = _EXPECTED_DTYPE[column]
    if expected == "object/string":
        return name in ("object", "string", "large_string") or pd.api.types.is_string_dtype(dtype)
    if expected == "bool/boolean":
        return name in ("bool", "boolean")
    return name == expected


def validate(out_dir: Path, reference_parquet: Path | None, segment_gap_seconds: float = 30.0) -> dict:
    parts = sorted(out_dir.glob("part_*.parquet"))
    checks: dict[str, dict] = {}
    if not parts:
        return {"passed": False, "error": f"no part_*.parquet in {out_dir}"}

    schema_problems = []
    dup_key_rows = 0
    unsorted_parts = []
    within_segment_dt_counts: dict[int, int] = {}
    bad_dt_parts = []
    rows = aircraft = segments = 0
    aircraft_set: set[str] = set()
    missingness = {name: 0 for name in FEATURES}

    for part in parts:
        df = pd.read_parquet(part)
        if list(df.columns) != list(CLEAN_COLUMNS):
            schema_problems.append({"part": part.name, "columns": list(df.columns)})
        else:
            for col in CLEAN_COLUMNS:
                if not _dtype_ok(col, df[col].dtype):
                    schema_problems.append({"part": part.name, "column": col, "dtype": str(df[col].dtype)})
        dup_key_rows += int(df.duplicated(["icao24", "time"], keep=False).sum())
        if not df[["icao24", "time"]].equals(df.sort_values(["icao24", "time"])[["icao24", "time"]]):
            unsorted_parts.append(part.name)
        dt = df.groupby(["icao24", "segment_id"], sort=False)["time"].diff().dropna()
        if dt.size:
            if (dt <= 0).any() or (dt > segment_gap_seconds).any():
                bad_dt_parts.append(part.name)
            for value, count in dt.astype(int).value_counts().items():
                within_segment_dt_counts[int(value)] = within_segment_dt_counts.get(int(value), 0) + int(count)
        rows += int(len(df))
        segments += int(df[["icao24", "segment_id"]].drop_duplicates().shape[0])
        aircraft_set.update(df["icao24"].unique().tolist())
        for name in FEATURES:
            missingness[name] += int(df[name].isna().sum())
    aircraft = len(aircraft_set)

    checks["schema_matches_contract"] = {"passed": not schema_problems, "problems": schema_problems[:10]}
    checks["natural_key_unique"] = {"passed": dup_key_rows == 0, "duplicate_rows": dup_key_rows}
    checks["sorted_by_icao_time"] = {"passed": not unsorted_parts, "unsorted_parts": unsorted_parts}
    modal_dt = max(within_segment_dt_counts, key=within_segment_dt_counts.get) if within_segment_dt_counts else None
    checks["within_segment_cadence_10s"] = {
        "passed": (not bad_dt_parts) and modal_dt == 10,
        "modal_dt_seconds": modal_dt,
        "dt_value_counts": dict(sorted(within_segment_dt_counts.items())),
        "parts_with_dt_out_of_range": bad_dt_parts,
    }

    # Split coverage and disjointness.
    split_check: dict = {"passed": False}
    split_path = out_dir / "split_aircraft.json"
    if split_path.exists():
        try:
            splits = load_split_aircraft(split_path)
            validate_splits(splits, aircraft_set)
            split_check = {"passed": True, "counts": splits.counts, "n_aircraft": len(splits.aircraft)}
        except Exception as error:  # noqa: BLE001 - report any split problem
            split_check = {"passed": False, "error": str(error)}
    else:
        split_check = {"passed": False, "error": "split_aircraft.json missing"}
    checks["split_coverage_and_disjoint"] = split_check

    comparison = {"hdd": {"rows": rows, "aircraft": aircraft, "segments": segments, "missingness": missingness}}
    if reference_parquet and Path(reference_parquet).exists():
        ref = pd.read_parquet(reference_parquet, columns=["icao24", "segment_id", *FEATURES])
        comparison["reference"] = {
            "rows": int(len(ref)),
            "aircraft": int(ref["icao24"].nunique()),
            "segments": int(ref[["icao24", "segment_id"]].drop_duplicates().shape[0]),
            "missingness": {name: int(ref[name].isna().sum()) for name in FEATURES},
        }

    report = {
        "out_dir": str(out_dir),
        "n_parts": len(parts),
        "checks": checks,
        "comparison_table": comparison,
        "passed": all(c["passed"] for c in checks.values()),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/processed/hdd_clean_v1"))
    parser.add_argument("--reference", type=Path, default=Path("data/processed/opensky_clean_v1.parquet"))
    parser.add_argument("--report", type=Path, default=Path("results/hdd_clean_v1_validation/report.json"))
    parser.add_argument("--segment-gap-seconds", type=float, default=30.0)
    args = parser.parse_args()
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    reference = args.reference if args.reference.is_absolute() else ROOT / args.reference
    report = validate(out_dir, reference, args.segment_gap_seconds)
    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"passed": report["passed"],
                      "checks": {k: v["passed"] for k, v in report["checks"].items()}}, indent=2, sort_keys=True))
    print(f"Wrote {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
