from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler


DEFAULT_SEED = 42
DEFAULT_SEQ_LEN = 30
DEFAULT_STRIDE = 10
DEFAULT_N_CLIENTS = 5
DEFAULT_LIMITS = {
    "train": 12_000,
    "val": 2_000,
    "test": 3_000,
}

INPUT_PATH = Path("data/processed/opensky_clean_v1.parquet")
OUT_DIR = Path("data/sequences_v2")

CONTINUOUS_FEATURES = [
    "lat",
    "lon",
    "velocity",
    "heading_sin",
    "heading_cos",
    "vertrate",
    "baroaltitude",
    "geoaltitude",
]

MISSING_FEATURES = [
    "lat_missing",
    "lon_missing",
    "velocity_missing",
    "heading_missing",
    "vertrate_missing",
    "baroaltitude_missing",
    "geoaltitude_missing",
]

FEATURES = CONTINUOUS_FEATURES + MISSING_FEATURES

CLASS_NAMES = {
    0: "normal",
    1: "position_spoof_sim",
    2: "velocity_anomaly_sim",
    3: "altitude_anomaly_sim",
    4: "replay_freeze_sim",
}

ATTACK_TARGETS = {
    1: {
        "name": "position_spoof_sim",
        "continuous": [0, 1],
        "missing": [8, 9],
        "features": ["lat", "lon"],
        "units": {"lat": "degrees", "lon": "degrees"},
    },
    2: {
        "name": "velocity_anomaly_sim",
        "continuous": [2],
        "missing": [10],
        "features": ["velocity"],
        "units": {"velocity": "m/s"},
    },
    3: {
        "name": "altitude_anomaly_sim",
        "continuous": [6, 7],
        "missing": [13, 14],
        "features": ["baroaltitude", "geoaltitude"],
        "units": {"baroaltitude": "m", "geoaltitude": "m"},
    },
    4: {
        "name": "replay_freeze_sim",
        "continuous": list(range(len(CONTINUOUS_FEATURES))),
        "missing": [8, 9, 10, 11, 12, 13, 14],
        "features": CONTINUOUS_FEATURES,
        "units": {name: "feature_native_unit" for name in CONTINUOUS_FEATURES},
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build v2 ADS-B sequence tensors with validated synthetic "
            "attack labels and unscaled binary missingness indicators."
        )
    )
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--seq-len", type=int, default=DEFAULT_SEQ_LEN)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--n-clients", type=int, default=DEFAULT_N_CLIENTS)
    parser.add_argument("--train-normal", type=int, default=DEFAULT_LIMITS["train"])
    parser.add_argument("--val-normal", type=int, default=DEFAULT_LIMITS["val"])
    parser.add_argument("--test-normal", type=int, default=DEFAULT_LIMITS["test"])
    parser.add_argument(
        "--sampling-mode",
        choices=["reservoir", "first_valid"],
        default="reservoir",
        help=(
            "reservoir scans all candidates for uniform sampling; first_valid "
            "stops after each class reservoir is full and is intended for "
            "lightweight smoke tests."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into an existing non-empty output directory.",
    )
    return parser.parse_args()


def ensure_output_dir(path: Path, force: bool) -> None:
    path.mkdir(parents=True, exist_ok=True)
    existing = [p for p in path.iterdir() if p.name != ".gitkeep"]
    if existing and not force:
        raise FileExistsError(
            f"{path} is not empty. Use --force only when you intend to "
            "replace v2 outputs. Baseline data/sequences is never touched."
        )


def choose_interval(
    window: np.ndarray,
    missing_idx: list[int],
    rng: np.random.Generator,
    min_len: int,
    max_len: int,
    min_start: int,
    max_end_exclusive: int,
) -> tuple[int, int] | None:
    n = len(window)
    max_end_exclusive = min(max_end_exclusive, n)
    candidates: list[tuple[int, int]] = []

    for start in range(min_start, max_end_exclusive):
        for length in range(min_len, max_len + 1):
            end = start + length
            if end > max_end_exclusive:
                continue
            flags = window[start:end, missing_idx]
            if np.all(flags == 0):
                candidates.append((start, end))

    if not candidates:
        return None

    return candidates[int(rng.integers(0, len(candidates)))]


def finite_interval(window: np.ndarray, start: int, end: int, idx: list[int]) -> bool:
    return bool(np.isfinite(window[start:end, idx]).all())


def interval_delta(
    before: np.ndarray,
    after: np.ndarray,
    start: int,
    end: int,
    idx: list[int],
) -> dict[str, float]:
    delta = np.abs(after[start:end, idx] - before[start:end, idx])
    return {
        CONTINUOUS_FEATURES[col_idx]: float(delta[:, pos].max())
        for pos, col_idx in enumerate(idx)
    }


def make_attack(
    window: np.ndarray,
    label: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict] | None:
    before = window
    attacked = before.copy()
    target = ATTACK_TARGETS[label]

    if label == 1:
        interval = choose_interval(
            before,
            target["missing"],
            rng,
            min_len=3,
            max_len=7,
            min_start=len(before) // 3,
            max_end_exclusive=len(before) - 2,
        )
        if interval is None:
            return None
        start, end = interval
        if not finite_interval(before, start, end, target["continuous"]):
            return None

        lat_shift = float(rng.choice([-0.15, 0.15]))
        lon_shift = float(rng.choice([-0.20, 0.20]))
        attacked[start:end, 0] += lat_shift
        attacked[start:end, 1] += lon_shift
        magnitudes = {"lat": lat_shift, "lon": lon_shift}

    elif label == 2:
        interval = choose_interval(
            before,
            target["missing"],
            rng,
            min_len=2,
            max_len=5,
            min_start=len(before) // 3,
            max_end_exclusive=len(before) - 2,
        )
        if interval is None:
            return None
        start, end = interval
        if not finite_interval(before, start, end, target["continuous"]):
            return None

        min_velocity = float(np.nanmin(before[start:end, 2]))
        if min_velocity < 90.0:
            shift = 80.0
        else:
            shift = float(rng.choice([-80.0, 80.0]))
        attacked[start:end, 2] += shift
        if np.any(attacked[start:end, 2] < 0):
            return None
        magnitudes = {"velocity": shift}

    elif label == 3:
        interval = choose_interval(
            before,
            target["missing"],
            rng,
            min_len=3,
            max_len=7,
            min_start=len(before) // 3,
            max_end_exclusive=len(before) - 2,
        )
        if interval is None:
            return None
        start, end = interval
        if not finite_interval(before, start, end, target["continuous"]):
            return None

        min_altitude = float(np.nanmin(before[start:end, [6, 7]]))
        if min_altitude < 3_000.0:
            shift = 2_500.0
        else:
            shift = float(rng.choice([-2_500.0, 2_500.0]))
        attacked[start:end, 6] += shift
        attacked[start:end, 7] += shift
        if np.any(attacked[start:end, [6, 7]] < -1_000.0):
            return None
        magnitudes = {"baroaltitude": shift, "geoaltitude": shift}

    elif label == 4:
        dynamic_idx = target["continuous"]
        candidates: list[tuple[int, int, int]] = []
        for anchor in range(4, len(before) - 6):
            for length in range(4, 9):
                start = anchor + 1
                end = start + length
                if end > len(before):
                    continue
                flags = before[anchor:end, target["missing"]]
                if not np.all(flags == 0):
                    continue
                if not finite_interval(before, anchor, end, dynamic_idx):
                    continue
                original_delta = np.abs(
                    before[start:end, dynamic_idx]
                    - before[anchor, dynamic_idx]
                )
                if float(original_delta.max()) <= 1e-6:
                    continue
                candidates.append((anchor, start, end))

        if not candidates:
            return None

        anchor, start, end = candidates[int(rng.integers(0, len(candidates)))]
        attacked[start:end, dynamic_idx] = before[anchor, dynamic_idx]
        magnitudes = interval_delta(before, attacked, start, end, dynamic_idx)

    else:
        raise ValueError(f"Unknown attack label: {label}")

    deltas = interval_delta(before, attacked, start, end, target["continuous"])
    effective = any(value > 1e-6 for value in deltas.values())
    if not effective:
        return None

    if label == 4:
        replay_constant = bool(
            np.allclose(
                attacked[start:end, target["continuous"]],
                attacked[start - 1, target["continuous"]],
                atol=1e-6,
                rtol=0.0,
            )
        )
        if not replay_constant:
            return None

    metadata = {
        "attack_type": target["name"],
        "attack_start_idx": int(start),
        "attack_end_idx": int(end),
        "attack_anchor_idx": int(start - 1) if label == 4 else None,
        "target_features_json": json.dumps(target["features"]),
        "magnitude_json": json.dumps(magnitudes, sort_keys=True),
        "units_json": json.dumps(target["units"], sort_keys=True),
        "max_abs_delta_json": json.dumps(deltas, sort_keys=True),
        "validation_passed": True,
    }
    return attacked, metadata


def maybe_keep(
    reservoir: list[tuple[np.ndarray, dict]],
    item: tuple[np.ndarray, dict],
    seen: int,
    limit: int,
    rng: np.random.Generator,
    sampling_mode: str,
) -> None:
    if sampling_mode == "first_valid" and len(reservoir) >= limit:
        return

    if len(reservoir) < limit:
        reservoir.append(item)
        return

    replace_at = int(rng.integers(0, seen))
    if replace_at < limit:
        reservoir[replace_at] = item


def collect_split_examples(
    df: pd.DataFrame,
    aircraft_ids: set[str],
    split: str,
    limit: int,
    seq_len: int,
    stride: int,
    rng: np.random.Generator,
    sampling_mode: str,
) -> tuple[dict[int, list[tuple[np.ndarray, dict]]], dict[int, int]]:
    reservoirs: dict[int, list[tuple[np.ndarray, dict]]] = {
        label: [] for label in CLASS_NAMES
    }
    seen = {label: 0 for label in CLASS_NAMES}

    subset = df[df["icao24"].isin(aircraft_ids)]
    candidate_window_id = 0

    def reservoirs_full() -> bool:
        return all(len(reservoirs[label]) >= limit for label in CLASS_NAMES)

    for (icao24, segment_id), group in subset.groupby(
        ["icao24", "segment_id"],
        sort=False,
    ):
        if sampling_mode == "first_valid" and reservoirs_full():
            break

        values = group[FEATURES].to_numpy(dtype=np.float32)
        times = group["time"].to_numpy()
        if len(values) < seq_len:
            continue

        for start in range(0, len(values) - seq_len + 1, stride):
            if sampling_mode == "first_valid" and reservoirs_full():
                break

            end = start + seq_len
            window = values[start:end].copy()
            origin = {
                "split": split,
                "source_window_id": int(candidate_window_id),
                "icao24": str(icao24),
                "segment_id": int(segment_id),
                "source_start_time": float(times[start]),
                "source_end_time": float(times[end - 1]),
                "source_start_offset": int(start),
                "source_end_offset": int(end - 1),
            }
            candidate_window_id += 1

            normal_meta = {
                **origin,
                "label": 0,
                "class_name": CLASS_NAMES[0],
                "attack_type": None,
                "attack_start_idx": None,
                "attack_end_idx": None,
                "attack_anchor_idx": None,
                "target_features_json": None,
                "magnitude_json": None,
                "units_json": None,
                "max_abs_delta_json": None,
                "validation_passed": True,
            }
            seen[0] += 1
            maybe_keep(
                reservoirs[0],
                (window, normal_meta),
                seen[0],
                limit,
                rng,
                sampling_mode,
            )

            for label in (1, 2, 3, 4):
                attack = make_attack(window, label, rng)
                if attack is None:
                    continue
                attacked_window, attack_meta = attack
                seen[label] += 1
                meta = {
                    **origin,
                    **attack_meta,
                    "label": label,
                    "class_name": CLASS_NAMES[label],
                }
                maybe_keep(
                    reservoirs[label],
                    (attacked_window, meta),
                    seen[label],
                    limit,
                    rng,
                    sampling_mode,
                )

    return reservoirs, seen


def fit_preprocessor(
    df: pd.DataFrame,
    train_ids: set[str],
) -> tuple[SimpleImputer, StandardScaler]:
    train_rows = df[df["icao24"].isin(train_ids)]
    continuous = train_rows[CONTINUOUS_FEATURES].to_numpy(dtype=np.float32)

    imputer = SimpleImputer(strategy="median")
    imputed = imputer.fit_transform(continuous)

    scaler = StandardScaler()
    scaler.fit(imputed)
    return imputer, scaler


def transform_windows(
    raw: np.ndarray,
    imputer: SimpleImputer,
    scaler: StandardScaler,
) -> np.ndarray:
    continuous = raw[:, :, : len(CONTINUOUS_FEATURES)]
    missing = raw[:, :, len(CONTINUOUS_FEATURES) :]

    shape = continuous.shape
    continuous_flat = continuous.reshape(-1, len(CONTINUOUS_FEATURES))
    continuous_flat = imputer.transform(continuous_flat)
    continuous_flat = scaler.transform(continuous_flat)
    continuous_scaled = continuous_flat.reshape(shape).astype(np.float32)

    missing_binary = np.nan_to_num(missing, nan=1.0).astype(np.float32)
    missing_binary = np.where(missing_binary > 0, 1.0, 0.0).astype(np.float32)
    return np.concatenate([continuous_scaled, missing_binary], axis=2)


def write_split(
    out_dir: Path,
    split: str,
    reservoirs: dict[int, list[tuple[np.ndarray, dict]]],
    imputer: SimpleImputer,
    scaler: StandardScaler,
    rng: np.random.Generator,
    n_clients: int,
) -> dict:
    items: list[tuple[np.ndarray, dict]] = []
    for label in sorted(reservoirs):
        items.extend(reservoirs[label])

    if not items:
        raise RuntimeError(f"No examples collected for split {split}.")

    raw = np.stack([item[0] for item in items]).astype(np.float32)
    rows = [item[1] for item in items]
    y = np.asarray([row["label"] for row in rows], dtype=np.int64)

    X = transform_windows(raw, imputer, scaler)

    order = rng.permutation(len(y))
    X = X[order]
    y = y[order]
    rows = [rows[int(i)] for i in order]

    for example_index, row in enumerate(rows):
        row["example_index"] = int(example_index)

    np.savez_compressed(out_dir / f"{split}.npz", X=X, y=y)
    pd.DataFrame(rows).to_parquet(out_dir / f"{split}_metadata.parquet", index=False)

    if split == "train":
        client_ids = rng.integers(0, n_clients, size=len(y), dtype=np.int32)
        np.save(out_dir / "train_client_ids.npy", client_ids)

    unique, counts = np.unique(y, return_counts=True)
    return {
        "examples": int(len(y)),
        "class_counts": {
            CLASS_NAMES[int(label)]: int(count)
            for label, count in zip(unique, counts)
        },
    }


def main() -> None:
    args = parse_args()
    limits = {
        "train": args.train_normal,
        "val": args.val_normal,
        "test": args.test_normal,
    }

    ensure_output_dir(args.out_dir, args.force)
    rng = np.random.default_rng(args.seed)

    columns = [
        "icao24",
        "segment_id",
        "time",
        *CONTINUOUS_FEATURES,
        *MISSING_FEATURES,
    ]
    print("Reading cleaned dataset:", args.input, flush=True)
    df = pd.read_parquet(args.input, columns=columns)
    df = df.sort_values(["icao24", "segment_id", "time"]).reset_index(drop=True)

    aircraft = np.asarray(df["icao24"].dropna().unique().astype(str).to_numpy()).copy()
    rng.shuffle(aircraft)

    n_aircraft = len(aircraft)
    train_end = int(n_aircraft * 0.70)
    val_end = int(n_aircraft * 0.85)

    split_ids = {
        "train": set(aircraft[:train_end]),
        "val": set(aircraft[train_end:val_end]),
        "test": set(aircraft[val_end:]),
    }
    print(
        "Aircraft split:",
        {name: len(ids) for name, ids in split_ids.items()},
        flush=True,
    )

    print(
        "Fitting training-only imputer and scaler for continuous features...",
        flush=True,
    )
    imputer, scaler = fit_preprocessor(df, split_ids["train"])

    np.savez(
        args.out_dir / "preprocessing_parameters.npz",
        continuous_medians=imputer.statistics_,
        continuous_scaler_mean=scaler.mean_,
        continuous_scaler_scale=scaler.scale_,
        continuous_feature_names=np.array(CONTINUOUS_FEATURES),
        missing_feature_names=np.array(MISSING_FEATURES),
        feature_names=np.array(FEATURES),
    )

    split_summary = {}
    candidate_summary = {}

    for split, ids in split_ids.items():
        print(
            f"\nBuilding {split} examples with limit {limits[split]} per class "
            f"using {args.sampling_mode} sampling...",
            flush=True,
        )
        reservoirs, seen = collect_split_examples(
            df=df,
            aircraft_ids=ids,
            split=split,
            limit=limits[split],
            seq_len=args.seq_len,
            stride=args.stride,
            rng=rng,
            sampling_mode=args.sampling_mode,
        )
        candidate_summary[split] = {
            CLASS_NAMES[label]: int(count) for label, count in seen.items()
        }
        for label, reservoir in reservoirs.items():
            if len(reservoir) < limits[split]:
                print(
                    f"  Warning: {split} {CLASS_NAMES[label]} has "
                    f"{len(reservoir)} valid examples; requested {limits[split]}."
                    ,
                    flush=True,
                )

        split_summary[split] = write_split(
            args.out_dir,
            split,
            reservoirs,
            imputer,
            scaler,
            rng,
            args.n_clients,
        )
        print("  Saved:", split_summary[split], flush=True)

    split_aircraft = {
        split: sorted(ids) for split, ids in split_ids.items()
    }
    with open(args.out_dir / "split_aircraft.json", "w", encoding="utf-8") as f:
        json.dump(split_aircraft, f, indent=2)

    metadata = {
        "version": "v2",
        "seed": args.seed,
        "input_path": str(args.input),
        "sequence_length": args.seq_len,
        "stride": args.stride,
        "n_clients": args.n_clients,
        "normal_limit_per_split": limits,
        "features": FEATURES,
        "continuous_features_scaled": CONTINUOUS_FEATURES,
        "missing_features_binary_unscaled": MISSING_FEATURES,
        "classes": CLASS_NAMES,
        "split_unit": "aircraft ICAO24",
        "sampling_mode": args.sampling_mode,
        "candidate_counts_seen": candidate_summary,
        "saved_split_summary": split_summary,
        "attack_generation": {
            "label_policy": (
                "An attack label is assigned only after the target interval "
                "is observed, finite, perturbed, and validated."
            ),
            "targets": ATTACK_TARGETS,
        },
    }
    with open(args.out_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("\nV2 sequence generation complete.")
    print("Output directory:", args.out_dir.resolve())


if __name__ == "__main__":
    main()
