from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_ROOT = Path("data/sequences_v2")

TARGET_MISSING_IDXS = {
    1: [8, 9],
    2: [10],
    3: [13, 14],
    4: [8, 9, 10, 11, 12, 13, 14],
}

TARGET_CONTINUOUS_IDXS = {
    1: [0, 1],
    2: [2],
    3: [6, 7],
    4: list(range(8)),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit v2 synthetic attack metadata and target intervals."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    return parser.parse_args()


def decode_json(value: object) -> dict | list | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return json.loads(str(value))


def interval_missing_fraction(
    X: np.ndarray,
    rows: pd.DataFrame,
    label: int,
) -> float:
    missing_idx = TARGET_MISSING_IDXS[label]
    values = []
    for row in rows.itertuples(index=False):
        start = int(row.attack_start_idx)
        end = int(row.attack_end_idx)
        example = X[int(row.example_index)]
        values.append(example[start:end][:, missing_idx])
    if not values:
        return float("nan")
    flat = np.concatenate([v.reshape(-1) for v in values])
    return float(flat.mean())


def replay_interval_constant_fraction(X: np.ndarray, rows: pd.DataFrame) -> float:
    checks = []
    idx = TARGET_CONTINUOUS_IDXS[4]
    for row in rows.itertuples(index=False):
        example = int(row.example_index)
        start = int(row.attack_start_idx)
        end = int(row.attack_end_idx)
        anchor = int(row.attack_anchor_idx)
        sequence = X[example]
        checks.append(
            bool(
                np.allclose(
                    sequence[start:end][:, idx],
                    sequence[anchor, idx],
                    atol=1e-6,
                    rtol=0.0,
                )
            )
        )
    if not checks:
        return float("nan")
    return float(np.mean(checks))


def max_recorded_delta(rows: pd.DataFrame) -> dict[str, float]:
    maxima: dict[str, float] = {}
    for value in rows["max_abs_delta_json"]:
        decoded = decode_json(value)
        if not decoded:
            continue
        for feature, delta in decoded.items():
            maxima[feature] = max(maxima.get(feature, 0.0), float(delta))
    return maxima


def audit_split(root: Path, split: str, class_names: dict[int, str]) -> None:
    with np.load(root / f"{split}.npz") as data:
        X = data["X"]
        y = data["y"]
    rows = pd.read_parquet(root / f"{split}_metadata.parquet")

    if not np.array_equal(y, rows["label"].to_numpy(dtype=np.int64)):
        raise AssertionError(f"{split}: y labels do not match metadata")

    print(f"\n{'=' * 12} {split.upper()} {'=' * 12}")
    print("shape:", X.shape)
    print("class counts:", np.bincount(y, minlength=5).astype(int).tolist())

    for label in (1, 2, 3, 4):
        subset = rows[rows["label"] == label].copy()
        if subset.empty:
            raise AssertionError(f"{split}: no examples for class {label}")

        if not subset["validation_passed"].astype(bool).all():
            raise AssertionError(f"{split}: class {label} has validation failures")

        missing_fraction = interval_missing_fraction(X, subset, label)
        starts = subset["attack_start_idx"].astype(int)
        ends = subset["attack_end_idx"].astype(int)
        durations = ends - starts
        deltas = max_recorded_delta(subset)

        print(f"\nClass {label}: {class_names[label]}")
        print("examples:", len(subset))
        print(
            "interval duration min/median/max:",
            [
                int(durations.min()),
                float(durations.median()),
                int(durations.max()),
            ],
        )
        print("target missing fraction in attack interval:", round(missing_fraction, 6))
        print("max recorded absolute delta:", deltas)

        if missing_fraction != 0.0:
            raise AssertionError(
                f"{split}: class {label} has target missingness inside "
                "validated attack intervals"
            )

        if label == 4:
            constant_fraction = replay_interval_constant_fraction(X, subset)
            print("replay interval constant fraction:", round(constant_fraction, 6))
            if constant_fraction != 1.0:
                raise AssertionError(
                    f"{split}: replay attack interval was not fully frozen"
                )


def main() -> None:
    args = parse_args()
    root = args.root
    with open(root / "metadata.json", "r", encoding="utf-8") as f:
        metadata = json.load(f)

    class_names = {int(k): v for k, v in metadata["classes"].items()}
    print("Auditing root:", root.resolve())
    print("Dataset version:", metadata.get("version"))
    print(
        "Label policy:",
        metadata["attack_generation"]["label_policy"],
    )

    for split in ("train", "val", "test"):
        audit_split(root, split, class_names)

    print("\nAttack audit complete.")


if __name__ == "__main__":
    main()
