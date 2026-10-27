"""Materialize a deterministic aircraft-hash subset of the HDD clean table (S7).

The clean table's parts are aircraft-hash buckets (build_hdd_dataset assigns
each aircraft to one part), so an aircraft's whole track is in one part. This
builder takes an INDEPENDENT hash sample of aircraft (fixed seed, default
fraction 0.10) and writes one parquet sorted by (icao24, segment_id, time) so
its file order equals the generator's source_row_id order. It records a content
fingerprint and verifies all four dates, all three splits, and global 5-degree
cell coverage survive the sample. Read-only w.r.t. the clean table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.attacks.fingerprint import content_fingerprint  # noqa: E402
from flids.attacks.splits import SPLIT_NAMES, load_split_aircraft  # noqa: E402


def sampled(icao24: str, seed: int, fraction: float) -> bool:
    """Deterministic, machine-independent aircraft-hash membership in the sample."""
    digest = hashlib.blake2b(f"subset|{seed}|{icao24}".encode(), digest_size=8).digest()
    return (int.from_bytes(digest, "big") / float(1 << 64)) < fraction


def build_subset(clean_dir: Path, out_path: Path, fraction: float, seed: int) -> dict:
    parts = sorted(clean_dir.glob("part_*.parquet"))
    if not parts:
        raise SystemExit(f"no part_*.parquet in {clean_dir}")
    frames = []
    for part in parts:
        df = pd.read_parquet(part)
        keep = df["icao24"].map(lambda c: sampled(str(c), seed, fraction)).to_numpy()
        if keep.any():
            frames.append(df[keep])
    if not frames:
        raise SystemExit("empty subset; raise the fraction")
    subset = pd.concat(frames, ignore_index=True).sort_values(
        ["icao24", "segment_id", "time"], kind="mergesort").reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subset.to_parquet(out_path, index=False)

    dates = sorted({datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d")
                    for t in subset["time"].to_numpy()})
    splits = load_split_aircraft(clean_dir / "split_aircraft.json")
    subset_split = subset["icao24"].map(splits.assignments)
    split_counts = {name: int(subset.loc[subset_split == name, "icao24"].nunique()) for name in SPLIT_NAMES}
    lat = subset["lat"].to_numpy(float); lon = subset["lon"].to_numpy(float)
    finite = np.isfinite(lat) & np.isfinite(lon)
    cells = {(int(np.floor((a + 90) / 5)), int(np.floor((b + 180) / 5)))
             for a, b in zip(lat[finite], lon[finite])}
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "clean_dir": str(clean_dir), "fraction": fraction, "seed": seed,
        "rows": int(len(subset)), "aircraft": int(subset["icao24"].nunique()),
        "segments": int(subset[["icao24", "segment_id"]].drop_duplicates().shape[0]),
        "dates": dates, "split_aircraft_counts": split_counts, "n_cells": len(cells),
        "content_fingerprint": content_fingerprint(subset),
        "sorted_by": ["icao24", "segment_id", "time"],
        "note": "file order == generator source_row_id order; use as both generation input and validator --source",
    }
    out_path.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    problems = []
    if len(dates) < 4:
        problems.append(f"only {len(dates)} dates present")
    if any(v == 0 for v in split_counts.values()):
        problems.append(f"a split is empty: {split_counts}")
    if len(cells) == 0:
        problems.append("no cells covered")
    manifest["coverage_ok"] = not problems
    manifest["coverage_problems"] = problems
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-dir", type=Path, default=Path("data/processed/hdd_clean_v1"))
    parser.add_argument("--fraction", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    clean_dir = args.clean_dir if args.clean_dir.is_absolute() else ROOT / args.clean_dir
    out = args.out or (ROOT / "data" / "processed" / f"hdd_clean_v1_subset_{int(args.fraction*100):02d}pct.parquet")
    out = out if out.is_absolute() else ROOT / out
    manifest = build_subset(clean_dir, out, args.fraction, args.seed)
    print(json.dumps({k: manifest[k] for k in ("rows", "aircraft", "segments", "dates",
                                               "split_aircraft_counts", "n_cells", "coverage_ok",
                                               "coverage_problems", "content_fingerprint")}, indent=2, sort_keys=True))
    print(f"Wrote {out}")
    return 0 if manifest["coverage_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
