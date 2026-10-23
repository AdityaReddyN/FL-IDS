"""Run train-only trivial shortcut baselines; this is pipeline validation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score


def summary_features(x: np.ndarray) -> np.ndarray:
    """Per-feature mean/std/min/max/mean absolute first difference."""
    diff = np.abs(np.diff(x, axis=1)).mean(axis=1)
    return np.concatenate([
        x.mean(axis=1), x.std(axis=1), x.min(axis=1), x.max(axis=1), diff,
    ], axis=1)


def _score(name: str, train_x: np.ndarray, train_y: np.ndarray,
           val_x: np.ndarray, val_y: np.ndarray, seed: int) -> dict:
    if len(np.unique(train_y)) < 2 or len(np.unique(val_y)) < 2:
        return {"name": name, "status": "unavailable_single_class"}
    model = LogisticRegression(max_iter=300, random_state=seed, solver="liblinear")
    model.fit(train_x, train_y)
    prob = model.predict_proba(val_x)[:, 1]
    predicted = (prob >= 0.5).astype(np.int64)
    return {
        "name": name, "status": "measured",
        "validation_roc_auc": float(roc_auc_score(val_y, prob)),
        "validation_balanced_accuracy": float(balanced_accuracy_score(val_y, predicted)),
    }


def run_audit(dataset_dir: Path, seed: int) -> dict:
    x_train = np.load(dataset_dir / "X_train.npy", mmap_mode="r")
    y_train = np.load(dataset_dir / "y_binary_train.npy")
    balanced = np.load(dataset_dir / "balanced_train_indices.npy")
    matched_val = np.load(dataset_dir / "missingness_matched_val_indices.npy")
    x_val = np.load(dataset_dir / "X_val.npy", mmap_mode="r")
    y_val = np.load(dataset_dir / "y_binary_val.npy")
    meta_train = pd.read_parquet(dataset_dir / "metadata_train.parquet")
    meta_val = pd.read_parquet(dataset_dir / "metadata_val.parquet")
    train_keep = balanced
    val_keep = np.flatnonzero(y_val >= 0)
    train_y = y_train[train_keep]
    val_y = y_val[val_keep]
    matched_y = y_val[matched_val]
    train_meta = meta_train.iloc[train_keep]
    val_meta = meta_val.iloc[val_keep]

    missing_train = np.asarray(x_train[train_keep, :, 8:].mean(axis=1))
    missing_val = np.asarray(x_val[val_keep, :, 8:].mean(axis=1))
    missing_matched_val = np.asarray(x_val[matched_val, :, 8:].mean(axis=1))
    # Position is normalized window offset within its own aircraft-segment;
    # it is never inferred from an attack mask or episode labels.
    def positions(meta):
        max_offset = meta.groupby(["icao24", "segment_id"]).start_offset.transform("max").to_numpy()
        return np.divide(meta.start_offset.to_numpy(dtype=float), max_offset,
                         out=np.zeros(len(meta), dtype=float), where=max_offset > 0).reshape(-1, 1)

    results = [
        _score("missingness_only", missing_train, train_y,
               missing_val, val_y, seed),
        _score("missingness_only_conditioned", missing_train, train_y,
               missing_matched_val, matched_y, seed),
        _score("position_within_segment_only", positions(train_meta), train_y,
               positions(val_meta), val_y, seed),
        _score("per_feature_summary_stats", summary_features(np.asarray(x_train[train_keep])), train_y,
               summary_features(np.asarray(x_val[val_keep])), val_y, seed),
        _score("per_feature_summary_stats_conditioned", summary_features(np.asarray(x_train[train_keep])), train_y,
               summary_features(np.asarray(x_val[matched_val])), matched_y, seed),
    ]
    return {
        "status": "pipeline_validation_only_not_scientific_result",
        "dataset": str(dataset_dir), "seed": seed,
        "train_rows": int(len(train_keep)), "validation_rows": int(len(val_keep)),
        "validation_attack_fraction": float(val_y.mean()) if len(val_y) else None,
        "ambiguous_validation_windows_excluded": int(np.count_nonzero(y_val < 0)),
        "missingness_matched_validation_rows": int(len(matched_val)),
        "missingness_matched_validation_attack_fraction": float(matched_y.mean()) if len(matched_y) else None,
        "contact_lag_seconds": "excluded from model features; not admitted pending separate leakage review",
        "results": results,
        "interpretation": "High shortcut scores indicate a dataset design problem; no near-chance threshold is silently assumed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/sequences_v3/seed_42"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = run_audit(args.dataset_dir, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
