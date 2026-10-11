
from pathlib import Path
import numpy as np

root = Path("data/sequences")

for split in ("train", "val", "test"):
    path = root / f"{split}.npz"

    with np.load(path) as data:
        X = data["X"]
        y = data["y"]

        print(f"\n{split.upper()}")
        print("X shape:", X.shape)
        print("y shape:", y.shape)
        print("dtype:", X.dtype)
        print("Finite values:", bool(np.isfinite(X).all()))
        print("Class counts:", np.bincount(y, minlength=5).tolist())

        assert X.ndim == 3
        assert X.shape[1] == 30
        assert len(X) == len(y)
        assert np.isfinite(X).all()
        assert set(np.unique(y)).issubset(set(range(5)))

clients = np.load(root / "train_client_ids.npy")
print("\nIID clients:", np.bincount(clients).tolist())
assert len(clients) == len(np.load(root / "train.npz")["y"])