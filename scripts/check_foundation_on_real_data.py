"""Read-only foundation checks against the real cleaned table and split file.

Run this manually after the synthetic unit tests pass:

    .venv/Scripts/python.exe scripts/check_foundation_on_real_data.py

The script reads immutable inputs, prints a JSON summary, and writes nothing.
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

from flids.attacks.config import load_config, validate_config  # noqa: E402
from flids.attacks.fingerprint import (  # noqa: E402
    content_fingerprint,
    schema_fingerprint,
)
from flids.attacks.keys import add_natural_keys, assert_natural_key_unique  # noqa: E402
from flids.attacks.manifest import build_manifest  # noqa: E402
from flids.attacks.splits import load_split_aircraft, validate_splits  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data" / "processed" / "opensky_clean_v1.parquet",
    )
    parser.add_argument(
        "--split",
        type=Path,
        default=ROOT / "data" / "sequences_v2" / "split_aircraft.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "attack_v3_stage1.yaml",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    before = args.input.stat()
    df = pd.read_parquet(args.input)

    key_columns = ["icao24", "segment_id", "time"]
    keys = add_natural_keys(df[key_columns])
    assert_natural_key_unique(keys)
    source_ids_are_positions = keys["source_row_id"].tolist() == list(range(len(keys)))
    offsets_in_range = bool(
        (keys["segment_row_offset"] >= 0).all()
    )

    aircraft = df["icao24"].unique()
    splits = load_split_aircraft(args.split)
    validate_splits(splits, expected_icao24=aircraft)

    config = load_config(args.config)
    validate_config(config)

    schema_sha = schema_fingerprint(df)
    content_sha = content_fingerprint(df)
    content_sha_second_read = content_fingerprint(pd.read_parquet(args.input))

    manifest = build_manifest(
        config_path=args.config,
        global_seed=int(config["global_seed"]),
        input_fingerprints={
            "cleaned_table_schema": schema_sha,
            "cleaned_table_content": content_sha,
        },
    )

    after = args.input.stat()
    summary = {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "unique_aircraft": int(len(aircraft)),
        "natural_key_unique": True,
        "source_row_id_is_position": source_ids_are_positions,
        "segment_row_offset_non_negative": offsets_in_range,
        "split_counts": splits.counts,
        "split_covers_cleaned_aircraft": True,
        "schema_fingerprint": schema_sha,
        "content_fingerprint": content_sha,
        "content_fingerprint_stable_on_reread": content_sha == content_sha_second_read,
        "config_status": config.get("status"),
        "config_requires_approval": config.get("status") != "approved",
        "manifest": manifest,
        "input_unchanged": (before.st_size, before.st_mtime_ns)
        == (after.st_size, after.st_mtime_ns),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
