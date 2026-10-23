from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import sklearn
import torch
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score,
                             roc_auc_score)
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flids.models.lstm import LSTMClassifier


def args_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a binary LSTM on v3 sequences.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/sequences_v3/seed_42_phase2"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--threads", type=int, default=2)
    return parser.parse_args()


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def load_split(path: Path, split: str) -> tuple[np.ndarray, np.ndarray]:
    x = np.load(path / f"X_{split}.npy", mmap_mode="r")
    y = np.load(path / f"y_binary_{split}.npy", mmap_mode="r")
    valid = np.asarray(y) >= 0
    if not np.isfinite(x).all():
        raise ValueError(f"non-finite values in {split} X")
    return np.asarray(x[valid], dtype=np.float32), np.asarray(y[valid], dtype=np.int64)


def main() -> int:
    args = args_parser()
    if args.out_dir.exists():
        raise FileExistsError(f"refusing to overwrite {args.out_dir}")
    start_time = time.perf_counter()
    seed_all(args.seed)
    torch.set_num_threads(args.threads)
    data_dir = args.data_dir
    X_train_all = np.load(data_dir / "X_train.npy", mmap_mode="r")
    y_train_all = np.load(data_dir / "y_binary_train.npy", mmap_mode="r")
    train_idx = np.load(data_dir / "balanced_train_indices.npy")
    X_train = X_train_all[train_idx]
    y_train = y_train_all[train_idx]
    if np.any(y_train < 0):
        raise ValueError("balanced training indices include ambiguous windows")
    X_val, y_val = load_split(data_dir, "val")
    X_test, y_test = load_split(data_dir, "test")
    device = torch.device("cpu")
    model = LSTMClassifier(X_train.shape[-1], args.hidden_size).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()
    train_loader = DataLoader(TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train)),
                              batch_size=args.batch_size, shuffle=True,
                              generator=torch.Generator().manual_seed(args.seed))
    val_loader = DataLoader(TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val)),
                            batch_size=512, shuffle=False)
    history: list[dict] = []
    best_score, best_epoch, stale = -1.0, 0, 0
    best_state: dict[str, torch.Tensor] | None = None
    for epoch in range(1, args.epochs + 1):
        model.train()
        loss_sum = 0.0
        for xb, yb in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(xb), yb)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.detach()) * len(yb)
        model.eval()
        val_scores, val_preds = [], []
        with torch.no_grad():
            for xb, _ in val_loader:
                logits = model(xb)
                val_scores.extend(torch.softmax(logits, dim=1)[:, 1].numpy())
                val_preds.extend(logits.argmax(dim=1).numpy())
        score = float(f1_score(y_val, val_preds, average="macro", zero_division=0))
        history.append({"epoch": epoch, "train_loss": loss_sum / len(y_train),
                        "val_macro_f1_at_0_5": score})
        if score > best_score:
            best_score, best_epoch, stale = score, epoch, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= args.patience:
                break
    if best_state is None:
        raise RuntimeError("no model checkpoint selected")
    model.load_state_dict(best_state)
    model.eval()
    probabilities = []
    with torch.no_grad():
        for start in range(0, len(X_test), 512):
            xb = torch.from_numpy(X_test[start:start + 512])
            probabilities.extend(torch.softmax(model(xb), dim=1)[:, 1].numpy())
    prob = np.asarray(probabilities)
    pred = (prob >= 0.5).astype(np.int64)
    normal = y_test == 0
    args.out_dir.mkdir(parents=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                            text=True, check=True).stdout.strip()
    metrics = {
        "roc_auc": float(roc_auc_score(y_test, prob)),
        "pr_auc": float(average_precision_score(y_test, prob)),
        "macro_f1_at_0_5": float(f1_score(y_test, pred, average="macro", zero_division=0)),
        "normal_fpr_at_0_5": float(np.mean(pred[normal] == 1)),
        "confusion_matrix_labels_0_1": confusion_matrix(y_test, pred, labels=[0, 1]).tolist(),
        "n_test": int(len(y_test)), "n_test_normal": int(normal.sum()),
        "n_test_attack": int((y_test == 1).sum()), "threshold": 0.5,
        "best_epoch": best_epoch, "best_val_macro_f1": best_score,
    }
    with (args.out_dir / "history.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(history[0]))
        writer.writeheader()
        writer.writerows(history)
    np.savetxt(args.out_dir / "test_predictions.csv",
               np.column_stack([y_test, prob]), delimiter=",", header="y_true,attack_probability",
               comments="")
    (args.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    config = {
        "data_dir": str(data_dir), "seed": args.seed, "model": "binary_lstm",
        "hidden_size": args.hidden_size, "batch_size": args.batch_size,
        "learning_rate": 1e-3, "max_epochs": args.epochs, "patience": args.patience,
        "selection_metric": "validation macro-F1 at threshold 0.5",
        "training_view": "binary_balanced_train_indices", "test_view": "realistic prevalence",
        "device": "cpu", "torch_version": torch.__version__, "numpy": np.__version__,
        "scikit_learn": sklearn.__version__, "git_commit": commit,
        "wall_seconds": time.perf_counter() - start_time,
        "caveat": "pipeline validation on synthetic labels over decoded OpenSky state vectors; not operational IDS evidence",
    }
    (args.out_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
