
from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

# --------------------------------------------------
# Configuration
# --------------------------------------------------
SEED = 42
SEQ_LEN = 30
STRIDE = 10
N_CLIENTS = 5

# Normal windows per split. Each gets one example of
# every synthetic attack class as well.
MAX_NORMAL = {
    "train": 12_000,
    "val": 2_000,
    "test": 3_000,
}

INPUT_PATH = Path("data/processed/opensky_clean_v1.parquet")
OUT_DIR = Path("data/sequences")
OUT_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(SEED)

BASE_FEATURES = [
    "lat", "lon", "velocity",
    "heading_sin", "heading_cos",
    "vertrate", "baroaltitude", "geoaltitude",
]

MISSING_FEATURES = [
    "lat_missing", "lon_missing", "velocity_missing",
    "heading_missing", "vertrate_missing",
    "baroaltitude_missing", "geoaltitude_missing",
]

FEATURES = BASE_FEATURES + MISSING_FEATURES

# Labels: 0 normal, 1 position, 2 velocity,
#         3 altitude, 4 replay-like freeze
CLASS_NAMES = {
    0: "normal",
    1: "position_spoof_sim",
    2: "velocity_anomaly_sim",
    3: "altitude_anomaly_sim",
    4: "replay_freeze_sim",
}


def reservoir_sample_windows(df, aircraft_ids, limit):
    """Uniform reservoir sample of valid window locations."""
    reservoir = []
    seen = 0

    subset = df[df["icao24"].isin(aircraft_ids)]

    for _, group in subset.groupby(
        ["icao24", "segment_id"], sort=False
    ):
        values = group[FEATURES].to_numpy(dtype=np.float32)

        if len(values) < SEQ_LEN:
            continue

        for start in range(0, len(values) - SEQ_LEN + 1, STRIDE):
            seen += 1
            item = values[start:start + SEQ_LEN].copy()

            if len(reservoir) < limit:
                reservoir.append(item)
            else:
                j = int(rng.integers(0, seen))
                if j < limit:
                    reservoir[j] = item

    if not reservoir:
        raise RuntimeError(
            "No valid windows found. Check segment IDs and data."
        )

    return np.stack(reservoir)


def make_attack(window, label):
    """Return a copy with one controlled synthetic perturbation."""
    x = window.copy()
    n = len(x)

    if label == 1:
        # Position displacement over a short section.
        # Latitude/longitude are in degrees.
        start = int(rng.integers(n // 3, max(n // 3 + 1, n - 5)))
        end = min(n, start + int(rng.integers(3, 8)))
        x[start:end, 0] += rng.choice([-0.15, 0.15])
        x[start:end, 1] += rng.choice([-0.20, 0.20])

    elif label == 2:
        # Inject a sharp velocity spike or drop in m/s.
        start = int(rng.integers(n // 3, max(n // 3 + 1, n - 5)))
        end = min(n, start + int(rng.integers(2, 6)))
        x[start:end, 2] += rng.choice([-80.0, 80.0])

    elif label == 3:
        # Inject an abrupt altitude shift in metres.
        start = int(rng.integers(n // 3, max(n // 3 + 1, n - 5)))
        end = min(n, start + int(rng.integers(3, 8)))
        shift = rng.choice([-2500.0, 2500.0])
        x[start:end, 6] += shift
        x[start:end, 7] += shift

    elif label == 4:
        # Freeze the dynamic state by repeating an earlier state.
        # Preserve the missingness flags as originally observed.
        freeze_at = int(rng.integers(5, n - 5))
        dynamic = x[freeze_at, :len(BASE_FEATURES)].copy()
        x[freeze_at + 1:, :len(BASE_FEATURES)] = dynamic

    return x


def main():
    print("Reading cleaned dataset...")
    columns = [
        "icao24", "segment_id", "time",
        *BASE_FEATURES, *MISSING_FEATURES,
    ]
    df = pd.read_parquet(INPUT_PATH, columns=columns)

    df = df.sort_values(
        ["icao24", "segment_id", "time"]
    ).reset_index(drop=True)

    # Split by aircraft BEFORE generating windows.
    aircraft = np.asarray(df["icao24"].dropna().unique().to_numpy(),dtype=str).copy()
    rng.shuffle(aircraft)

    n = len(aircraft)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    train_ids = set(aircraft[:train_end])
    val_ids = set(aircraft[train_end:val_end])
    test_ids = set(aircraft[val_end:])

    print(
        f"Aircraft split: train={len(train_ids)}, "
        f"val={len(val_ids)}, test={len(test_ids)}"
    )

    # Fit imputation and scaling ONLY on training aircraft.
    train_rows = df[df["icao24"].isin(train_ids)]
    train_values = train_rows[FEATURES].to_numpy(dtype=np.float32)

    imputer = SimpleImputer(strategy="median")
    train_imputed = imputer.fit_transform(train_values)

    scaler = StandardScaler()
    scaler.fit(train_imputed)

    # Save preprocessing parameters for reproducibility.
    np.savez(
        OUT_DIR / "preprocessing_parameters.npz",
        medians=imputer.statistics_,
        scaler_mean=scaler.mean_,
        scaler_scale=scaler.scale_,
        feature_names=np.array(FEATURES),
    )

    split_ids = {
        "train": train_ids,
        "val": val_ids,
        "test": test_ids,
    }

    for split, ids in split_ids.items():
        print(f"\nBuilding {split} sequences...")

        raw_normal = reservoir_sample_windows(
            df, ids, MAX_NORMAL[split]
        )

        # Impute missing feature values per feature using
        # medians estimated from training aircraft only.
        shape = raw_normal.shape
        flat = raw_normal.reshape(-1, len(FEATURES))
        flat = imputer.transform(flat)
        raw_normal = flat.reshape(shape).astype(np.float32)

        X_list = [raw_normal]
        y_list = [
            np.zeros(len(raw_normal), dtype=np.int64)
        ]

        # Generate one synthetic example per attack class
        # for every selected normal window.
        for attack_label in (1, 2, 3, 4):
            print(f"  Generating class {attack_label}...")
            attacked = np.stack([
                make_attack(w, attack_label)
                for w in raw_normal
            ])

            attacked_flat = attacked.reshape(
                -1, len(FEATURES)
            )
            attacked_flat = imputer.transform(attacked_flat)
            attacked = attacked_flat.reshape(
                attacked.shape
            ).astype(np.float32)

            X_list.append(attacked)
            y_list.append(
                np.full(
                    len(attacked),
                    attack_label,
                    dtype=np.int64,
                )
            )

        X_raw = np.concatenate(X_list, axis=0)
        y = np.concatenate(y_list, axis=0)

        # Scale with training-only parameters.
        X = scaler.transform(
            X_raw.reshape(-1, len(FEATURES))
        ).reshape(X_raw.shape).astype(np.float32)

        # Shuffle within each split.
        order = rng.permutation(len(y))
        X = X[order]
        y = y[order]

        save_path = OUT_DIR / f"{split}.npz"
        np.savez_compressed(save_path, X=X, y=y)

        unique, counts = np.unique(y, return_counts=True)
        print("Saved:", save_path)
        print("Shape:", X.shape)
        print("Classes:", {
            CLASS_NAMES[int(k)]: int(v)
            for k, v in zip(unique, counts)
        })

        # IID client assignments are made for TRAIN ONLY.
        if split == "train":
            client_ids = rng.integers(
                0, N_CLIENTS, size=len(y), dtype=np.int32
            )
            np.save(
                OUT_DIR / "train_client_ids.npy",
                client_ids,
            )

            client_counts = np.bincount(
                client_ids, minlength=N_CLIENTS
            )
            print("IID client sample counts:", client_counts.tolist())

    metadata = {
        "seed": SEED,
        "sequence_length": SEQ_LEN,
        "stride": STRIDE,
        "n_clients": N_CLIENTS,
        "features": FEATURES,
        "classes": CLASS_NAMES,
        "split_unit": "aircraft ICAO24",
        "attack_labels": "synthetic controlled simulations",
        "client_partition": "random IID sample assignment",
    }

    with open(OUT_DIR / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("\nDataset generation complete.")
    print("Output directory:", OUT_DIR.resolve())


if __name__ == "__main__":
    main()