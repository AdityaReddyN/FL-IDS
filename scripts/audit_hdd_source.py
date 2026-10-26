"""Read-only audit of the HDD OpenSky archives (data/hdd_data/*.csv.tar).

Run this yourself; it STREAMS each ``.csv.tar`` without permanently extracting
it, is resumable per archive (skips archives whose per-archive JSON already
exists), and NEVER writes under ``data/hdd_data``. It generates no attacks,
windows, datasets, or resampled data: the resampling rule is a human decision
(Stage S4). It writes one JSON per archive plus a combined ``summary.json``.

The six reported areas (per `nextSteps.md` S3): schema, time coverage, per-track
cadence, aircraft recurrence, data quality, and a resampling compute-budget
estimate. See ``docs/hdd_audit_report_template.md`` for the human decisions the
results feed into.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.data.hdd_audit import (  # noqa: E402
    aircraft_recurrence,
    cadence_shares,
    cell_coverage,
    column_schema_diff,
    dt_quantiles,
    resample_count_estimate,
)

HDD_DIR = Path("data/hdd_data")
_README_MAX_BYTES = 2048


def _read_inner_csv(tar: tarfile.TarFile):
    """Return (csv_member_name, DataFrame, readme_head) streamed from the tar."""
    csv_member = None
    readme_head = None
    for member in tar.getmembers():
        lower = member.name.lower()
        if lower.endswith(".csv") and csv_member is None:
            csv_member = member
        elif "readme" in lower and readme_head is None:
            handle = tar.extractfile(member)
            if handle is not None:
                readme_head = handle.read(_README_MAX_BYTES).decode("utf-8", "replace")
    if csv_member is None:
        raise ValueError("no .csv member found in archive")
    handle = tar.extractfile(csv_member)
    frame = pd.read_csv(io.BytesIO(handle.read()))
    frame.columns = frame.columns.str.strip()
    return csv_member.name, frame, readme_head


def _pooled_track_dt(df: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Pooled within-aircraft consecutive dt, and the share of tracks with a >30 s gap."""
    dts = []
    tracks_with_gap = 0
    n_tracks = 0
    for _icao, group in df.sort_values(["icao24", "time"]).groupby("icao24", sort=False):
        times = group["time"].to_numpy(dtype=float)
        if times.size < 2:
            continue
        n_tracks += 1
        dt = np.diff(times)
        dts.append(dt)
        if np.any(dt > 30.0):
            tracks_with_gap += 1
    pooled = np.concatenate(dts) if dts else np.empty(0)
    gap_share = (tracks_with_gap / n_tracks) if n_tracks else None
    return pooled, gap_share


def audit_archive(path: Path) -> dict:
    """Stream and summarize one ``.csv.tar`` archive (read-only, in memory)."""
    with tarfile.open(path, "r") as tar:
        member_name, df, readme_head = _read_inner_csv(tar)

    schema = column_schema_diff(df.columns)
    has_time = "time" in df.columns
    has_icao = "icao24" in df.columns
    time_values = pd.to_numeric(df["time"], errors="coerce").to_numpy(float) if has_time else np.empty(0)
    finite_time = time_values[np.isfinite(time_values)]

    pooled_dt, gap_share = (_pooled_track_dt(df) if has_time and has_icao else (np.empty(0), None))

    quality = {}
    for col in schema["observed"]:
        if col in df.columns:
            quality[f"missing_{col}"] = int(df[col].isna().sum())
    if "onground" in df.columns:
        og = df["onground"].astype("string").str.strip().str.lower()
        quality["onground_true_share"] = float((og == "true").mean()) if len(og) else None
    if has_time and has_icao:
        quality["duplicate_icao_time_rows"] = int(df.duplicated(["icao24", "time"], keep=False).sum())
        quality["is_sorted_by_icao_time"] = bool(
            df[["icao24", "time"]].equals(df.sort_values(["icao24", "time"])[["icao24", "time"]])
        )
    for col in ("velocity", "heading"):
        if col in df.columns:
            values = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
            values = values[np.isfinite(values)]
            quality[f"{col}_range"] = [float(values.min()), float(values.max())] if values.size else None
    if "lastcontact" in df.columns and has_time:
        lag = finite_time - pd.to_numeric(df["lastcontact"], errors="coerce").to_numpy(float)[:finite_time.size]
        lag = lag[np.isfinite(lag)]
        quality["lastcontact_lag_seconds"] = (
            {"min": float(lag.min()), "median": float(np.median(lag)), "max": float(lag.max())}
            if lag.size else None
        )

    coverage = (cell_coverage(df["lat"], df["lon"]) if {"lat", "lon"}.issubset(df.columns)
                else {"n_points": 0})

    date_hours = sorted({
        datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%dT%H")
        for t in finite_time
    }) if finite_time.size else []

    return {
        "archive": path.name,
        "inner_csv": member_name,
        "readme_head": readme_head,
        "schema": schema,
        "rows": int(len(df)),
        "n_unique_aircraft": int(df["icao24"].nunique()) if has_icao else 0,
        "aircraft": sorted(map(str, df["icao24"].unique())) if has_icao else [],
        "time": {
            "min": float(finite_time.min()) if finite_time.size else None,
            "max": float(finite_time.max()) if finite_time.size else None,
            "date_hours": date_hours,
        },
        "cadence": {
            **cadence_shares(pooled_dt),
            "dt_quantiles": dt_quantiles(np.concatenate([[0.0], np.cumsum(pooled_dt)]) if pooled_dt.size else []),
            "share_tracks_with_gap_gt_30s": gap_share,
        },
        "quality": quality,
        "cell_coverage": coverage,
        "resample_estimate": {
            "decimate_mod10": resample_count_estimate(finite_time, "decimate_mod10"),
            "nearest_10s": resample_count_estimate(finite_time, "nearest_10s"),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HDD_DIR)
    parser.add_argument("--max-archives", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("results/hdd_audit_v1"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input if args.input.is_absolute() else ROOT / args.input
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    if out_dir.resolve() == (ROOT / HDD_DIR).resolve() or (ROOT / HDD_DIR).resolve() in out_dir.resolve().parents:
        raise SystemExit("refusing to write the audit under data/hdd_data")
    archives = sorted(input_dir.glob("*.csv.tar"))
    if args.max_archives is not None:
        archives = archives[: args.max_archives]
    if not archives:
        raise SystemExit(f"no .csv.tar archives found in {input_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    per_archive = []
    for archive in archives:
        per_path = out_dir / f"{archive.name}.json"
        if per_path.exists():  # resumable: skip already-audited archives
            per_archive.append(json.loads(per_path.read_text(encoding="utf-8")))
            print(f"skip (done): {archive.name}", flush=True)
            continue
        print(f"auditing: {archive.name}", flush=True)
        summary = audit_archive(archive)
        per_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        per_archive.append(summary)

    hours = {h: set() for item in per_archive for h in item["time"]["date_hours"]}
    dates = {}
    for item in per_archive:
        for h in item["time"]["date_hours"]:
            hours.setdefault(h, set()).update(item["aircraft"])
            dates.setdefault(h.split("T")[0], set()).update(item["aircraft"])
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(input_dir),
        "n_archives": len(per_archive),
        "rows_total": sum(item["rows"] for item in per_archive),
        "covered_date_hours": sorted(hours),
        "covered_dates": sorted(dates),
        "rows_per_archive": {item["archive"]: item["rows"] for item in per_archive},
        "aircraft_recurrence_across_hours": aircraft_recurrence(hours),
        "aircraft_recurrence_across_dates": aircraft_recurrence(dates),
        "any_schema_mismatch": [item["archive"] for item in per_archive if not item["schema"]["matches_contract"]],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Archives audited: {summary['n_archives']}; rows total: {summary['rows_total']:,}")
    print(f"Covered dates: {summary['covered_dates']}")
    print(f"Aircraft recurring across dates: "
          f"{summary['aircraft_recurrence_across_dates']['aircraft_in_multiple_buckets']:,}")
    print(f"Wrote {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    main()
