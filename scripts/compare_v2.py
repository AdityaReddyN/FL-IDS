import numpy as np
from pathlib import Path
a = Path("data/sequences_v2")
b = Path("data/reproductions/phase0/sequences_v2_seed42")
for s in ("train", "val", "test"):
    fb = b / f"{s}.npz"
    if not fb.exists():
        print(s, "MISSING in repro"); continue
    with np.load(a / f"{s}.npz") as x, np.load(fb) as y:
        print(s, "X equal:", np.array_equal(x["X"], y["X"]),
              "| y equal:", np.array_equal(x["y"], y["y"]))
ca, cb = b / "train_client_ids.npy", a / "train_client_ids.npy"
if ca.exists() and cb.exists():
    print("client ids equal:", np.array_equal(np.load(ca), np.load(cb)))
