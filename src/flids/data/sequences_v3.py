"""Build Phase 2 windows from immutable Stage C row-level tables.

Model features contain eight continuous channels and seven explicit
missingness channels. Continuous values are imputed/scaled using only unique
rows visible in train windows. `onground`, contact lag, and the configured
30-second stale-data diagnostic are retained as auxiliary arrays, never model
features. The 30-second flag threshold is an implementation choice.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


CONTINUOUS_FEATURES = (
    "mod_lat", "mod_lon", "mod_velocity", "heading_sin", "heading_cos",
    "mod_vertrate", "mod_baroaltitude", "mod_geoaltitude",
)
MISSING_FEATURES = (
    "lat_missing", "lon_missing", "velocity_missing", "heading_missing",
    "vertrate_missing", "baroaltitude_missing", "geoaltitude_missing",
)
FEATURE_NAMES = CONTINUOUS_FEATURES + MISSING_FEATURES
ATTACK_FAMILIES = (
    "constant_deviation", "random_gaussian_deviation", "gradual_deviation",
    "altitude_constant_deviation", "replay_partial_field",
    "replay_full_field", "freeze_fixed_value",
)
CLASS_NAMES = ("normal",) + ATTACK_FAMILIES
SPLITS = ("train", "val", "test")


def _match_controls(
    labels: np.ndarray,
    missing_counts: np.ndarray,
    rng: np.random.Generator,
    *,
    n_attacks: int | None = None,
) -> np.ndarray:
    """Pair attacks with unique normal windows of equal/nearest missing count."""
    attacks = np.flatnonzero(labels == 1)
    normals = np.flatnonzero(labels == 0)
    count = min(len(attacks), len(normals)) if n_attacks is None else min(n_attacks, len(attacks), len(normals))
    if count == 0:
        return np.array([], dtype=np.int64)
    attacks = rng.permutation(attacks)[:count]
    available: dict[int, list[int]] = {}
    for index in normals:
        available.setdefault(int(missing_counts[index]), []).append(int(index))
    for indices in available.values():
        rng.shuffle(indices)
    selected_normals: list[int] = []
    for attack_index in attacks:
        desired = int(missing_counts[attack_index])
        keys = [key for key, indices in available.items() if indices]
        nearest = min(keys, key=lambda key: (abs(key - desired), key))
        selected_normals.append(available[nearest].pop())
    paired = np.concatenate([attacks, np.asarray(selected_normals, dtype=np.int64)])
    return paired[rng.permutation(len(paired))]


def _continuous_frame(rows: pd.DataFrame) -> np.ndarray:
    heading = np.deg2rad(pd.to_numeric(rows["mod_heading"], errors="coerce").to_numpy(dtype=float))
    base = np.column_stack([
        rows["mod_lat"].to_numpy(dtype=float),
        rows["mod_lon"].to_numpy(dtype=float),
        rows["mod_velocity"].to_numpy(dtype=float),
        np.sin(heading), np.cos(heading),
        rows["mod_vertrate"].to_numpy(dtype=float),
        rows["mod_baroaltitude"].to_numpy(dtype=float),
        rows["mod_geoaltitude"].to_numpy(dtype=float),
    ])
    return base


def _metadata(records: list[dict]) -> pd.DataFrame:
    columns = (
        "window_id", "icao24", "segment_id", "split", "start_offset", "label",
        "stratum", "episode_id", "attack_family", "attack_subtype", "tier",
        "n_attack_rows", "n_effective_rows",
    )
    return pd.DataFrame.from_records(records, columns=columns)


def build_sequence_arrays(
    attacked_rows: pd.DataFrame,
    windows: pd.DataFrame,
    *,
    seed: int,
    stale_threshold_seconds: float = 30.0,
) -> dict[str, object]:
    """Return split tensors, labels, metadata, aux diagnostics, and train scaler.

    Ambiguous windows are retained with labels ``-1`` for auditability. The
    balanced training index excludes them and undersamples the majority binary
    class to the minority count using the supplied seed.
    """
    if not np.isfinite(stale_threshold_seconds) or stale_threshold_seconds < 0:
        raise ValueError("stale_threshold_seconds must be finite and non-negative")
    required_rows = {
        "icao24", "segment_id", "segment_row_offset", "split", "mod_heading",
        "onground", "contact_lag_seconds", "contact_lag_missing", "is_attack_row",
        "episode_position", "episode_id", *[f"mod_{x}" for x in (
            "lat", "lon", "velocity", "vertrate", "baroaltitude", "geoaltitude")],
    }
    required_windows = {
        "window_id", "icao24", "segment_id", "split", "start_offset", "n_rows",
        "label", "stratum", "episode_id", "attack_family", "attack_subtype", "tier",
        "n_attack_rows", "n_effective_rows",
    }
    if missing := required_rows - set(attacked_rows.columns):
        raise ValueError(f"attacked_rows missing columns: {sorted(missing)}")
    if missing := required_windows - set(windows.columns):
        raise ValueError(f"windows missing columns: {sorted(missing)}")
    if attacked_rows.duplicated(["icao24", "segment_id", "segment_row_offset"]).any():
        raise ValueError("duplicate natural row key")
    row_splits = attacked_rows.groupby("icao24", dropna=False).split.nunique()
    if (row_splits != 1).any():
        raise ValueError("aircraft occurs in more than one split")
    win_splits = windows.groupby("icao24", dropna=False).split.nunique()
    if (win_splits != 1).any() or not set(windows.split).issubset(set(SPLITS)):
        raise ValueError("window aircraft split is inconsistent")
    split_by_aircraft = attacked_rows.drop_duplicates("icao24").set_index("icao24").split
    if any(split_by_aircraft.get(row.icao24) != row.split for row in windows.itertuples()):
        raise ValueError("window split does not match source aircraft split")
    unknown_families = set(windows.loc[windows.label != "normal", "attack_family"].dropna()) - set(ATTACK_FAMILIES)
    if unknown_families:
        raise ValueError(f"unknown attack family: {sorted(unknown_families)}")

    grouped_rows = {}
    for key, group in attacked_rows.groupby(["icao24", "segment_id"], sort=False):
        segment = group.sort_values("segment_row_offset", kind="stable").reset_index(drop=True)
        offsets = segment.segment_row_offset.to_numpy()
        if not np.array_equal(offsets, np.arange(len(segment))):
            raise ValueError(f"segment row offsets are not contiguous from zero: {key}")
        grouped_rows[key] = {
            "frame": segment,
            "continuous": _continuous_frame(segment),
            "contact": segment.contact_lag_seconds.to_numpy(dtype=float),
            "contact_missing": segment.contact_lag_missing.to_numpy(dtype=bool),
            "onground": segment.onground.to_numpy(dtype=bool),
        }
    ordered_windows = windows.sort_values(
        ["split", "icao24", "segment_id", "start_offset", "window_id"], kind="stable"
    ).reset_index(drop=True)
    raw_by_split: dict[str, list[np.ndarray]] = {s: [] for s in SPLITS}
    aux_by_split: dict[str, list[np.ndarray]] = {s: [] for s in SPLITS}
    labels_by_split: dict[str, list[tuple[int, int]]] = {s: [] for s in SPLITS}
    metadata_by_split: dict[str, list[dict]] = {s: [] for s in SPLITS}
    train_row_masks: dict[tuple[str, int], np.ndarray] = {}

    for window in ordered_windows.itertuples(index=False):
        split = str(window.split)
        key = (str(window.icao24), int(window.segment_id))
        segment_data = grouped_rows.get(key)
        if segment_data is None:
            raise ValueError(f"window refers to missing segment {key}")
        start, count = int(window.start_offset), int(window.n_rows)
        if count != 30 or start < 0 or start + count > len(segment_data["continuous"]):
            raise ValueError(f"window range is outside segment {key}")
        continuous = segment_data["continuous"][start:start + count]
        missing = (~np.isfinite(continuous[:, [0, 1, 2, 3, 5, 6, 7]])).astype(np.float32)
        feature_values = np.column_stack([continuous, missing])
        raw_by_split[split].append(feature_values)
        contact = segment_data["contact"][start:start + count]
        contact_missing = segment_data["contact_missing"][start:start + count]
        onground = segment_data["onground"][start:start + count]
        stale = np.isfinite(contact) & (contact > stale_threshold_seconds)
        aux_by_split[split].append(np.column_stack([
            contact, contact_missing.astype(float), onground.astype(float), stale.astype(float),
        ]).astype(np.float32))
        label = str(window.label)
        if label == "normal":
            binary, multiclass = 0, 0
        elif label == "ambiguous":
            binary, multiclass = -1, -1
        else:
            binary = 1
            multiclass = ATTACK_FAMILIES.index(str(window.attack_family)) + 1
        labels_by_split[split].append((binary, multiclass))
        metadata_by_split[split].append({
            "window_id": int(window.window_id), "icao24": str(window.icao24),
            "segment_id": int(window.segment_id), "split": split,
            "start_offset": start, "label": label, "stratum": str(window.stratum),
            "episode_id": int(window.episode_id),
            "attack_family": None if pd.isna(window.attack_family) else str(window.attack_family),
            "attack_subtype": None if pd.isna(window.attack_subtype) else str(window.attack_subtype),
            "tier": None if pd.isna(window.tier) else str(window.tier),
            "n_attack_rows": int(window.n_attack_rows),
            "n_effective_rows": int(window.n_effective_rows),
        })
        if split == "train":
            mask = train_row_masks.setdefault(key, np.zeros(len(segment_data["continuous"]), dtype=bool))
            mask[start:start + count] = True

    if not raw_by_split["train"]:
        raise ValueError("training windows are required to fit preprocessing")
    train_source_values = np.concatenate([
        grouped_rows[key]["continuous"][mask]
        for key, mask in sorted(train_row_masks.items())
    ], axis=0)
    finite = np.isfinite(train_source_values)
    counts = finite.sum(axis=0)
    if np.any(counts == 0):
        raise ValueError("a continuous feature is entirely missing in training rows")
    means = np.where(finite, train_source_values, 0.0).sum(axis=0) / counts
    imputed_train = np.where(np.isfinite(train_source_values), train_source_values, means)
    scales = imputed_train.std(axis=0)
    scales[~np.isfinite(scales) | (scales == 0)] = 1.0

    built: dict[str, object] = {
        "feature_names": FEATURE_NAMES,
        "class_names": CLASS_NAMES,
        "scaler_mean": means.astype(np.float64),
        "scaler_scale": scales.astype(np.float64),
        "stale_threshold_seconds": float(stale_threshold_seconds),
    }
    for split in SPLITS:
        values = raw_by_split[split]
        raw = np.stack(values).astype(np.float32) if values else np.empty((0, 30, len(FEATURE_NAMES)), np.float32)
        continuous_part = raw[:, :, :8].astype(np.float64)
        masks = raw[:, :, 8:]
        imputed = np.where(np.isfinite(continuous_part), continuous_part, means.reshape(1, 1, -1))
        scaled = ((imputed - means.reshape(1, 1, -1)) / scales.reshape(1, 1, -1)).astype(np.float32)
        built[f"X_{split}"] = np.concatenate([scaled, masks], axis=2)
        label_array = np.asarray(labels_by_split[split], dtype=np.int64).reshape(-1, 2)
        built[f"y_binary_{split}"] = label_array[:, 0]
        built[f"y_multiclass_{split}"] = label_array[:, 1]
        built[f"metadata_{split}"] = _metadata(metadata_by_split[split])
        built[f"aux_{split}"] = np.stack(aux_by_split[split]).astype(np.float32) if aux_by_split[split] else np.empty((0, 30, 4), np.float32)

    rng = np.random.default_rng(seed)
    train_missing_counts = built["X_train"][:, :, 8:].sum(axis=(1, 2)).astype(np.int64)
    built["balanced_train_indices"] = _match_controls(
        built["y_binary_train"], train_missing_counts, rng,
    )
    val_missing_counts = built["X_val"][:, :, 8:].sum(axis=(1, 2)).astype(np.int64)
    built["missingness_matched_val_indices"] = _match_controls(
        built["y_binary_val"], val_missing_counts, rng,
    )
    return built


def save_sequence_dataset(
    built: Mapping[str, object], output_dir: str | Path, *, config: Mapping[str, object]
) -> dict:
    """Create a new v3 output directory with arrays, metadata, config, manifest."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    counts = {}
    file_hashes = {}
    for key, value in built.items():
        if key in {"feature_names", "class_names", "scaler_mean", "scaler_scale", "stale_threshold_seconds"}:
            continue
        if isinstance(value, pd.DataFrame):
            value.to_parquet(target / f"{key}.parquet", index=False)
            counts[key] = len(value)
            file_path = target / f"{key}.parquet"
        else:
            np.save(target / f"{key}.npy", np.asarray(value), allow_pickle=False)
            counts[key] = int(np.asarray(value).shape[0])
            file_path = target / f"{key}.npy"
        digest = hashlib.sha256()
        with file_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        file_hashes[file_path.name] = digest.hexdigest()
    np.savez(target / "preprocessing.npz", mean=built["scaler_mean"], scale=built["scaler_scale"])
    preprocessing_path = target / "preprocessing.npz"
    file_hashes[preprocessing_path.name] = hashlib.sha256(preprocessing_path.read_bytes()).hexdigest()
    manifest = {
        "dataset_version": "sequences_v3", "source_type": "decoded OpenSky state vectors",
        "labels": "synthetic data-layer simulation; not operational ADS-B security evidence",
        "feature_names": list(built["feature_names"]), "class_names": list(built["class_names"]),
        "counts": counts, "table_sha256": file_hashes,
        "stale_threshold_seconds": built["stale_threshold_seconds"],
        "preprocessing": "continuous train-row mean imputation and standardization; missing flags appended unscaled",
        "config": dict(config),
    }
    (target / "config.json").write_text(json.dumps(dict(config), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
