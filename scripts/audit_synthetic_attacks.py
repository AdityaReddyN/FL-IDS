
from pathlib import Path
import numpy as np

ROOT = Path("data/sequences")

# Feature order used by build_sequence.py
FEATURES = [
    "lat", "lon", "velocity",
    "heading_sin", "heading_cos",
    "vertrate", "baroaltitude", "geoaltitude",
    "lat_missing", "lon_missing", "velocity_missing",
    "heading_missing", "vertrate_missing",
    "baroaltitude_missing", "geoaltitude_missing",
]

TARGETS = {
    1: ("position", [0, 1], [8, 9]),
    2: ("velocity", [2], [10]),
    3: ("altitude", [6, 7], [13, 14]),
    4: ("replay freeze", [0, 1, 2, 3, 4, 5, 6, 7], []),
}

for split in ("train", "val", "test"):
    path = ROOT / f"{split}.npz"

    with np.load(path) as data:
        X, y = data["X"], data["y"]

    print(f"\n{'=' * 12} {split.upper()} {'=' * 12}")

    for label, (name, target_idx, missing_idx) in TARGETS.items():
        subset = X[y == label]

        if len(subset) == 0:
            print(f"{name}: NO EXAMPLES")
            continue

        # Values are scaled. These are diagnostics, not
        # physical-unit thresholds.
        target = subset[:, :, target_idx]
        changes = np.abs(np.diff(target, axis=1))

        print(f"\nClass {label}: {name}")
        print("Examples:", len(subset))
        print(
            "Mean absolute adjacent change by target feature:",
            np.round(changes.mean(axis=(0, 1)), 4).tolist()
        )

        if missing_idx:
            missing_flags = subset[:, :, missing_idx]
            print(
                "Fraction of target-feature positions marked missing:",
                round(float(missing_flags.mean()), 4)
            )

        if label == 4:
            dynamic = subset[:, :, :8]
            frozen_fraction = np.all(
                np.isclose(dynamic[:, 1:, :], dynamic[:, :-1, :]),
                axis=(1, 2)
            ).mean()
            print(
                "Fraction with every dynamic feature constant "
                "throughout the whole window:",
                round(float(frozen_fraction), 4)
            )

print("\nAudit complete. Compare attack classes with normal class 0.")
print("These diagnostics do not by themselves prove label validity.")