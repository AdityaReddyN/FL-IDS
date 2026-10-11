from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_ROOT = Path("data/sequences_v2")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate v2 sequence tensors, metadata, and split hygiene."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    return parser.parse_args()


def assert_binary_missingness(X: np.ndarray, missing_start: int) -> None:
    missing = X[:, :, missing_start:]
    unique = np.unique(missing)
    if not np.isin(unique, [0.0, 1.0]).all():
        raise AssertionError(
            "Missingness indicators must remain binary 0/1 after preprocessing; "
            f"found values such as {unique[:10].tolist()}."
        )


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_split(root: Path, split: str, metadata: dict) -> dict:
    npz_path = root / f"{split}.npz"
    meta_path = root / f"{split}_metadata.parquet"

    if not npz_path.exists():
        raise FileNotFoundError(npz_path)
    if not meta_path.exists():
        raise FileNotFoundError(meta_path)

    with np.load(npz_path) as data:
        X = data["X"]
        y = data["y"]

    rows = pd.read_parquet(meta_path)

    feature_count = len(metadata["features"])
    missing_start = len(metadata["continuous_features_scaled"])

    if X.ndim != 3:
        raise AssertionError(f"{split}: X must be 3D, got shape {X.shape}")
    if X.shape[0] != len(y):
        raise AssertionError(f"{split}: X/y length mismatch")
    if X.shape[0] != len(rows):
        raise AssertionError(f"{split}: X/metadata length mismatch")
    if X.shape[2] != feature_count:
        raise AssertionError(
            f"{split}: expected {feature_count} features, got {X.shape[2]}"
        )
    if not np.isfinite(X).all():
        raise AssertionError(f"{split}: X contains non-finite values")
    if not set(np.unique(y)).issubset(set(range(5))):
        raise AssertionError(f"{split}: unexpected labels {np.unique(y).tolist()}")

    assert_binary_missingness(X, missing_start)

    if not np.array_equal(y, rows["label"].to_numpy(dtype=np.int64)):
        raise AssertionError(f"{split}: y labels do not match metadata labels")

    attack_rows = rows[rows["label"] != 0]
    if attack_rows.empty:
        raise AssertionError(f"{split}: no attack-labelled examples found")
    if not attack_rows["validation_passed"].astype(bool).all():
        failed = attack_rows.loc[~attack_rows["validation_passed"].astype(bool)]
        raise AssertionError(
            f"{split}: {len(failed)} attack rows failed validation metadata"
        )

    if rows["source_window_id"].isna().any():
        raise AssertionError(f"{split}: source_window_id contains missing values")

    counts = np.bincount(y, minlength=5)
    print(f"\n{split.upper()}")
    print("X shape:", X.shape)
    print("y shape:", y.shape)
    print("finite:", bool(np.isfinite(X).all()))
    print("class counts:", counts.tolist())
    print("missingness values:", np.unique(X[:, :, missing_start:]).tolist())
    print("metadata rows:", len(rows))

    return {
        "examples": int(len(y)),
        "class_counts": counts.astype(int).tolist(),
        "metadata_rows": int(len(rows)),
    }


def validate_aircraft_splits(root: Path) -> None:
    split_path = root / "split_aircraft.json"
    if not split_path.exists():
        raise FileNotFoundError(split_path)

    split_aircraft = load_json(split_path)
    train = set(split_aircraft["train"])
    val = set(split_aircraft["val"])
    test = set(split_aircraft["test"])

    overlaps = {
        "train_val": len(train & val),
        "train_test": len(train & test),
        "val_test": len(val & test),
    }
    if any(overlaps.values()):
        raise AssertionError(f"Aircraft split overlap detected: {overlaps}")

    print("\nAircraft split sizes:")
    print({"train": len(train), "val": len(val), "test": len(test)})
    print("Aircraft split overlaps:", overlaps)


def validate_clients(root: Path) -> None:
    client_path = root / "train_client_ids.npy"
    train_path = root / "train.npz"
    if not client_path.exists():
        raise FileNotFoundError(client_path)

    clients = np.load(client_path)
    with np.load(train_path) as data:
        y = data["y"]

    if len(clients) != len(y):
        raise AssertionError("train_client_ids length does not match train labels")

    print("\nTrain IID client counts:", np.bincount(clients).tolist())
    print("Train client/class counts:")
    for client_id in sorted(np.unique(clients).tolist()):
        print(
            int(client_id),
            np.bincount(y[clients == client_id], minlength=5).astype(int).tolist(),
        )


def main() -> None:
    args = parse_args()
    root = args.root

    metadata_path = root / "metadata.json"
    preprocess_path = root / "preprocessing_parameters.npz"
    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)
    if not preprocess_path.exists():
        raise FileNotFoundError(preprocess_path)

    metadata = load_json(metadata_path)
    with np.load(preprocess_path, allow_pickle=True) as params:
        feature_names = params["feature_names"].tolist()
        continuous = params["continuous_feature_names"].tolist()
        missing = params["missing_feature_names"].tolist()

    if feature_names != metadata["features"]:
        raise AssertionError("Preprocessing feature_names do not match metadata")
    if continuous != metadata["continuous_features_scaled"]:
        raise AssertionError("Continuous feature names do not match metadata")
    if missing != metadata["missing_features_binary_unscaled"]:
        raise AssertionError("Missing feature names do not match metadata")

    print("Validating root:", root.resolve())
    print("Dataset version:", metadata.get("version"))

    summary = {}
    for split in ("train", "val", "test"):
        summary[split] = validate_split(root, split, metadata)

    validate_aircraft_splits(root)
    validate_clients(root)

    print("\nValidation complete.")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
