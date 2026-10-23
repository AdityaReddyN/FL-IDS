"""Build the Phase 2 sequence dataset from a completed Stage C output."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import pyarrow
import sklearn

from flids.data.sequences_v3 import build_sequence_arrays, save_sequence_dataset


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/attack_generation_v3/stage1_seed_42_retry4"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/sequences_v3/seed_42_phase2"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--stale-threshold-seconds", type=float, default=30.0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    input_dir = args.input_dir if args.input_dir.is_absolute() else root / args.input_dir
    output_dir = args.out_dir if args.out_dir.is_absolute() else root / args.out_dir
    if output_dir.exists():
        parser.error(f"refusing to overwrite existing output directory: {output_dir}")
    manifest_path = input_dir / "manifest.json"
    rows_path, windows_path = input_dir / "attacked_rows.parquet", input_dir / "windows.parquet"
    for path in (manifest_path, rows_path, windows_path):
        if not path.is_file():
            parser.error(f"required input not found: {path}")
    input_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = pd.read_parquet(rows_path)
    windows = pd.read_parquet(windows_path)
    built = build_sequence_arrays(
        rows, windows, seed=args.seed,
        stale_threshold_seconds=args.stale_threshold_seconds,
    )
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True,
        ).strip())
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
        dirty = None
    config = {
        "seed": args.seed,
        "input_dir": str(input_dir.relative_to(root)),
        "input_manifest_sha256": sha256(manifest_path),
        "attacked_rows_sha256": sha256(rows_path),
        "windows_sha256": sha256(windows_path),
        "source_git_commit": input_manifest.get("git_commit"),
        "builder_git_commit": commit,
        "builder_git_dirty": dirty,
        "builder_sources_sha256": {
            "module": sha256(root / "src/flids/data/sequences_v3.py"),
            "script": sha256(Path(__file__).resolve()),
        },
        "python": sys.version.split()[0], "numpy": np.__version__,
        "pandas": pd.__version__, "pyarrow": pyarrow.__version__,
        "scikit_learn": sklearn.__version__,
        "stale_threshold_seconds": args.stale_threshold_seconds,
        "window_rows": 30, "stride": 10,
    }
    save_sequence_dataset(built, output_dir, config=config)
    print(json.dumps({"output_dir": str(output_dir), "counts": {
        split: len(built[f"metadata_{split}"]) for split in ("train", "val", "test")
    }, "balanced_train_rows": len(built["balanced_train_indices"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
