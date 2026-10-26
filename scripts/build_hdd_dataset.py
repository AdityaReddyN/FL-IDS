"""Build a cleaned HDD OpenSky table (new versioned output) + a global split.

Human-run, memory-bounded, resumable. Two passes so ``segment_id`` gets correct
per-aircraft time order at ~207 M rows without holding the whole table:

  Pass A  stream every archive (contract columns only) and append its rows to
          one of ``--buckets`` files chosen by a stable hash of ``icao24`` -- so
          every row for an aircraft lands in the same bucket.
  Pass B  load one bucket at a time (all rows for its aircraft, across dates),
          run the shared cleaner (sort by icao24,time; *_missing; heading sin/cos;
          contact_lag; segment_id at >30 s gaps), and write one clean part.

No resampling (D-041: the data is already ~10 s). Feature values are never edited
(velocity glitches are preserved and only counted). Output schema equals
``opensky_clean_v1``. The output is a NEW versioned directory; the 2-hour split
(``data/sequences_v2/split_aircraft.json``) is never reused for HDD aircraft.

This writes derived data (gitignored) and refuses a dirty Git worktree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flids.data.clean import CLEAN_COLUMNS, FEATURES, finalize_clean, normalize_raw  # noqa: E402
from flids.data.hdd_io import find_archives, read_archive  # noqa: E402

SPLIT_FRACTIONS = {"train": 0.70, "val": 0.15, "test": 0.15}  # cumulative 0.70 / 0.85 / 1.0

_BUCKET_SCHEMA = pa.schema([
    ("time", pa.int64()), ("icao24", pa.string()),
    *[(name, pa.float64()) for name in FEATURES],
    ("onground", pa.string()), ("lastcontact", pa.float64()),
])


def _stable_fraction(icao24: str, seed: int) -> float:
    """Deterministic [0,1) hash of an aircraft id (machine-independent)."""
    digest = hashlib.blake2b(f"{seed}|{icao24}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(1 << 64)


def assign_split(icao24: str, seed: int) -> str:
    """Global aircraft-level split by hashed ``icao24`` (70/15/15)."""
    u = _stable_fraction(icao24, seed)
    if u < SPLIT_FRACTIONS["train"]:
        return "train"
    if u < SPLIT_FRACTIONS["train"] + SPLIT_FRACTIONS["val"]:
        return "val"
    return "test"


def _bucket_of(icao24: str, seed: int, n_buckets: int) -> int:
    digest = hashlib.blake2b(f"bucket|{seed}|{icao24}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % n_buckets


def _bucket_table(df: pd.DataFrame) -> pa.Table:
    out = df.reindex(columns=[f.name for f in _BUCKET_SCHEMA])
    out["onground"] = out["onground"].astype("string")
    return pa.Table.from_pandas(out, schema=_BUCKET_SCHEMA, preserve_index=False)


def _git_state(root: Path) -> tuple[str, bool | None]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        return "unknown", None
    return commit, dirty


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/hdd_data"))
    parser.add_argument("--out", type=Path, default=Path("data/processed/hdd_clean_v1"))
    parser.add_argument("--buckets", type=int, default=64)
    parser.add_argument("--segment-gap-seconds", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--velocity-glitch-mps", type=float, default=400.0,
                        help="diagnostic threshold; values above are counted, never dropped")
    parser.add_argument("--keep-buckets", action="store_true", help="keep the temporary bucket files")
    return parser.parse_args()


def build(input_dir: Path, out_dir: Path, *, buckets: int, segment_gap_seconds: float,
          seed: int, velocity_glitch_mps: float, keep_buckets: bool,
          repo_root: Path = ROOT) -> dict:
    """Run both passes and write the clean parts, split file, and manifest."""
    archives = find_archives(input_dir)
    if not archives:
        raise SystemExit(f"no .csv.tar archives found in {input_dir}")
    if out_dir.exists():
        raise SystemExit(f"refusing to overwrite existing output directory: {out_dir}")
    bucket_dir = out_dir / "_buckets"
    bucket_dir.mkdir(parents=True, exist_ok=False)

    # --- Pass A: stream archives into hash-of-icao24 buckets --------------
    writers: dict[int, pq.ParquetWriter] = {}
    aircraft: set[str] = set()
    rows_per_archive: dict[str, int] = {}
    raw_rows = 0
    try:
        for archive in archives:
            _member, frame, _observed, _readme = read_archive(archive)
            frame = normalize_raw(frame)
            rows_per_archive[archive.name] = int(len(frame))
            raw_rows += int(len(frame))
            aircraft.update(frame["icao24"].unique().tolist())
            bucket_ids = frame["icao24"].map(lambda c: _bucket_of(c, seed, buckets))
            for bucket_id, part in frame.groupby(bucket_ids, sort=False):
                if bucket_id not in writers:
                    writers[bucket_id] = pq.ParquetWriter(
                        bucket_dir / f"bucket_{bucket_id:04d}.parquet", _BUCKET_SCHEMA, compression="zstd"
                    )
                writers[bucket_id].write_table(_bucket_table(part))
    finally:
        for writer in writers.values():
            writer.close()

    # --- Global aircraft-level split -------------------------------------
    split = {"train": [], "val": [], "test": []}
    for icao in sorted(aircraft):
        split[assign_split(icao, seed)].append(icao)
    (out_dir / "split_aircraft.json").write_text(json.dumps(split, indent=2), encoding="utf-8")

    # --- Pass B: clean each bucket into one part -------------------------
    clean_rows = 0
    segment_count = 0
    missingness = {name: 0 for name in FEATURES}
    velocity_glitch_rows = 0
    time_min = None
    time_max = None
    parts = []
    for bucket_path in sorted(bucket_dir.glob("bucket_*.parquet")):
        raw = pd.read_parquet(bucket_path)
        if raw.empty:
            continue
        clean = finalize_clean(raw, segment_gap_seconds)
        part_path = out_dir / f"part_{bucket_path.stem.split('_')[1]}.parquet"
        clean.to_parquet(part_path, index=False)
        parts.append(part_path)
        clean_rows += int(len(clean))
        segment_count += int(clean[["icao24", "segment_id"]].drop_duplicates().shape[0])
        for name in FEATURES:
            missingness[name] += int(clean[name].isna().sum())
        velocity_glitch_rows += int((clean["velocity"].abs() > velocity_glitch_mps).sum())
        tmin, tmax = int(clean["time"].min()), int(clean["time"].max())
        time_min = tmin if time_min is None else min(time_min, tmin)
        time_max = tmax if time_max is None else max(time_max, tmax)

    if not keep_buckets:
        shutil.rmtree(bucket_dir)

    commit, dirty = _git_state(repo_root)
    manifest = {
        "dataset_version": "hdd_clean_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "source": "decoded OpenSky state vectors (HDD archives), not raw 112-bit ADS-B messages",
        "input_dir": str(input_dir),
        "n_archives": len(archives),
        "segment_gap_seconds": segment_gap_seconds,
        "resampling": "none (data is already ~10 s, D-041)",
        "builder_git_commit": commit,
        "builder_git_dirty": dirty,
        "schema_columns": list(CLEAN_COLUMNS),
        "raw_rows_read": raw_rows,
        "rows": clean_rows,
        "aircraft": len(aircraft),
        "segments": segment_count,
        "split_counts": {name: len(ids) for name, ids in split.items()},
        "missingness": missingness,
        "velocity_glitch_rows_over_threshold": {"threshold_mps": velocity_glitch_mps, "rows": velocity_glitch_rows},
        "time_min": time_min, "time_max": time_max,
        "rows_per_archive": rows_per_archive,
        "parts": {p.name: {"rows": int(len(pd.read_parquet(p, columns=["time"]))),
                           "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(parts)},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "config.json").write_text(json.dumps({
        "seed": seed, "buckets": buckets, "segment_gap_seconds": segment_gap_seconds,
        "velocity_glitch_mps": velocity_glitch_mps,
        "python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
        "pyarrow": pa.__version__,
    }, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> int:
    args = parse_args()
    input_dir = args.input if args.input.is_absolute() else ROOT / args.input
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    _commit, dirty = _git_state(ROOT)
    if dirty:
        raise SystemExit("refusing to build a dataset from a dirty Git worktree; commit first")
    manifest = build(
        input_dir, out_dir, buckets=args.buckets, segment_gap_seconds=args.segment_gap_seconds,
        seed=args.seed, velocity_glitch_mps=args.velocity_glitch_mps, keep_buckets=args.keep_buckets,
    )
    print(json.dumps({"output_dir": str(out_dir), "rows": manifest["rows"],
                      "aircraft": manifest["aircraft"], "segments": manifest["segments"],
                      "split_counts": manifest["split_counts"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
