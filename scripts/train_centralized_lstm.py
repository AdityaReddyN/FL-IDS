from __future__ import annotations

import argparse
import csv
import json
import random
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from torch import nn
from torch.utils.data import DataLoader, Dataset


DATA_DIR = Path("data/sequences_v2")
RESULTS_DIR = Path("results/centralized_lstm")


class SequenceDataset(Dataset):
    def __init__(self, X: np.ndarray, y: np.ndarray) -> None:
        self.X = torch.from_numpy(X)
        self.y = torch.from_numpy(y.astype(np.int64, copy=False))

    def __len__(self) -> int:
        return int(self.y.shape[0])

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.X[idx], self.y[idx]


class LSTMClassifier(nn.Module):
    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int,
        num_classes: int,
        dropout: float,
    ) -> None:
        super().__init__()
        lstm_dropout = dropout if num_layers > 1 else 0.0
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=lstm_dropout,
        )
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h_n, _) = self.lstm(x)
        last_hidden = h_n[-1]
        return self.classifier(self.dropout(last_hidden))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a centralized multiclass LSTM baseline on v2 sequences."
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--run-name", type=str, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--torch-threads", type=int, default=0)
    parser.add_argument(
        "--eval-batch-size",
        type=int,
        default=512,
        help="Batch size for validation and test inference.",
    )
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def load_metadata(data_dir: Path) -> dict:
    path = data_dir / "metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing v2 metadata file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    if metadata.get("version") != "v2":
        raise ValueError(f"Expected v2 metadata, found {metadata.get('version')!r}")
    return metadata


def load_split(data_dir: Path, split: str) -> tuple[np.ndarray, np.ndarray]:
    path = data_dir / f"{split}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing split file: {path}")
    with np.load(path) as data:
        X = data["X"].astype(np.float32, copy=False)
        y = data["y"].astype(np.int64, copy=False)
    return X, y


def validate_split(
    split: str,
    X: np.ndarray,
    y: np.ndarray,
    expected_seq_len: int,
    expected_features: int,
    num_classes: int,
) -> list[int]:
    if X.ndim != 3:
        raise ValueError(f"{split}: expected 3D X, got shape {X.shape}")
    if X.shape[1] != expected_seq_len:
        raise ValueError(
            f"{split}: expected sequence length {expected_seq_len}, got {X.shape[1]}"
        )
    if X.shape[2] != expected_features:
        raise ValueError(
            f"{split}: expected {expected_features} features, got {X.shape[2]}"
        )
    if len(X) != len(y):
        raise ValueError(f"{split}: X/y length mismatch")
    if not np.isfinite(X).all():
        raise ValueError(f"{split}: X contains non-finite values")
    labels = np.unique(y)
    if not set(labels.tolist()).issubset(set(range(num_classes))):
        raise ValueError(f"{split}: unexpected labels {labels.tolist()}")
    return np.bincount(y, minlength=num_classes).astype(int).tolist()


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> tuple[float, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device)

        optimizer.zero_grad(set_to_none=True)
        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        loss.backward()
        optimizer.step()

        batch_size = int(y_batch.shape[0])
        total_loss += float(loss.item()) * batch_size
        correct += int((logits.argmax(dim=1) == y_batch).sum().item())
        total += batch_size

    return total_loss / total, correct / total


@torch.no_grad()
def predict(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, np.ndarray, np.ndarray]:
    model.eval()
    total_loss = 0.0
    total = 0
    y_true_parts: list[np.ndarray] = []
    y_pred_parts: list[np.ndarray] = []

    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device)
        logits = model(X_batch)
        loss = criterion(logits, y_batch)

        batch_size = int(y_batch.shape[0])
        total_loss += float(loss.item()) * batch_size
        total += batch_size
        y_true_parts.append(y_batch.cpu().numpy())
        y_pred_parts.append(logits.argmax(dim=1).cpu().numpy())

    return (
        total_loss / total,
        np.concatenate(y_true_parts),
        np.concatenate(y_pred_parts),
    )


def metrics_dict(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    class_names: dict[int, str],
) -> dict:
    labels = sorted(class_names)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        zero_division=0,
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    normal_label = 0
    normal_mask = y_true == normal_label
    clean_false_positive_rate = float(np.mean(y_pred[normal_mask] != normal_label))

    per_class = {}
    for idx, label in enumerate(labels):
        per_class[str(label)] = {
            "name": class_names[label],
            "precision": float(precision[idx]),
            "recall": float(recall[idx]),
            "f1": float(f1[idx]),
            "support": int(support[idx]),
        }

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro")),
        "clean_false_positive_rate": clean_false_positive_rate,
        "per_class": per_class,
        "confusion_matrix": cm.astype(int).tolist(),
    }


def write_history(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_confusion_matrix(path: Path, matrix: list[list[int]], class_names: dict[int, str]) -> None:
    labels = sorted(class_names)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["true_label", *[f"pred_{label}_{class_names[label]}" for label in labels]])
        for label, row in zip(labels, matrix):
            writer.writerow([f"{label}_{class_names[label]}", *row])


def main() -> None:
    args = parse_args()
    start_time = time.perf_counter()
    set_seed(args.seed)
    if args.torch_threads > 0:
        torch.set_num_threads(args.torch_threads)

    device = torch.device("cpu")
    metadata = load_metadata(args.data_dir)
    class_names = {int(k): v for k, v in metadata["classes"].items()}
    num_classes = len(class_names)
    expected_seq_len = int(metadata["sequence_length"])
    expected_features = len(metadata["features"])

    run_name = args.run_name or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.results_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=False)

    print("Centralized LSTM baseline")
    print("Device:", device)
    print("Torch:", torch.__version__)
    print("Run directory:", run_dir)
    print("Classes:", class_names)
    print("Features:", expected_features)

    X_train, y_train = load_split(args.data_dir, "train")
    X_val, y_val = load_split(args.data_dir, "val")
    X_test, y_test = load_split(args.data_dir, "test")

    split_counts = {
        "train": validate_split("train", X_train, y_train, expected_seq_len, expected_features, num_classes),
        "val": validate_split("val", X_val, y_val, expected_seq_len, expected_features, num_classes),
        "test": validate_split("test", X_test, y_test, expected_seq_len, expected_features, num_classes),
    }
    print("Class counts:", split_counts)

    train_loader = DataLoader(
        SequenceDataset(X_train, y_train),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
    )
    val_loader = DataLoader(
        SequenceDataset(X_val, y_val),
        batch_size=args.eval_batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )
    test_loader = DataLoader(
        SequenceDataset(X_test, y_test),
        batch_size=args.eval_batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    model = LSTMClassifier(
        input_size=expected_features,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        num_classes=num_classes,
        dropout=args.dropout,
    ).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)

    config = {
        "seed": args.seed,
        "hidden_size": args.hidden_size,
        "num_layers": args.num_layers,
        "dropout": args.dropout,
        "batch_size": args.batch_size,
        "eval_batch_size": args.eval_batch_size,
        "learning_rate": args.learning_rate,
        "epochs": args.epochs,
        "patience": args.patience,
        "num_workers": args.num_workers,
        "torch_threads": torch.get_num_threads(),
        "device": str(device),
        "torch_version": torch.__version__,
        "data_dir": str(args.data_dir),
        "class_names": class_names,
        "feature_names": metadata["features"],
        "split_counts": split_counts,
        "selection_criterion": "validation macro-F1",
        "synthetic_label_note": (
            "Synthetic attack labels support feasibility benchmarking only; "
            "they do not establish operational aviation IDS performance."
        ),
    }
    with open(run_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    best_macro_f1 = -1.0
    best_epoch = 0
    epochs_without_improvement = 0
    history: list[dict] = []
    best_path = run_dir / "best_model.pt"

    for epoch in range(1, args.epochs + 1):
        epoch_start = time.perf_counter()
        train_loss, train_acc = run_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, y_val_true, y_val_pred = predict(model, val_loader, criterion, device)
        val_metrics = metrics_dict(y_val_true, y_val_pred, class_names)
        val_acc = val_metrics["accuracy"]
        val_macro_f1 = val_metrics["macro_f1"]
        elapsed = time.perf_counter() - epoch_start

        improved = val_macro_f1 > best_macro_f1 + 1e-8
        if improved:
            best_macro_f1 = val_macro_f1
            best_epoch = epoch
            epochs_without_improvement = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "config": config,
                    "epoch": epoch,
                    "validation_macro_f1": val_macro_f1,
                },
                best_path,
            )
        else:
            epochs_without_improvement += 1

        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_accuracy": train_acc,
            "val_loss": val_loss,
            "val_accuracy": val_acc,
            "val_macro_f1": val_macro_f1,
            "best_epoch": best_epoch,
            "epoch_seconds": elapsed,
        }
        history.append(row)
        write_history(run_dir / "history.csv", history)
        print(
            f"epoch={epoch:03d} train_loss={train_loss:.4f} "
            f"train_acc={train_acc:.4f} val_loss={val_loss:.4f} "
            f"val_acc={val_acc:.4f} val_macro_f1={val_macro_f1:.4f} "
            f"best_epoch={best_epoch} seconds={elapsed:.1f}",
            flush=True,
        )

        if epochs_without_improvement >= args.patience:
            print(
                f"Early stopping after {epoch} epochs; best epoch was {best_epoch}.",
                flush=True,
            )
            break

    checkpoint = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    test_loss, y_test_true, y_test_pred = predict(model, test_loader, criterion, device)
    test_metrics = metrics_dict(y_test_true, y_test_pred, class_names)
    test_metrics["test_loss"] = float(test_loss)
    test_metrics["best_epoch"] = int(best_epoch)
    test_metrics["best_validation_macro_f1"] = float(best_macro_f1)
    test_metrics["total_seconds"] = float(time.perf_counter() - start_time)

    with open(run_dir / "test_metrics.json", "w", encoding="utf-8") as f:
        json.dump(test_metrics, f, indent=2)
    write_confusion_matrix(
        run_dir / "confusion_matrix.csv",
        test_metrics["confusion_matrix"],
        class_names,
    )
    with open(run_dir / "test_predictions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["example_index", "true_label", "predicted_label"])
        for idx, (truth, pred) in enumerate(zip(y_test_true.tolist(), y_test_pred.tolist())):
            writer.writerow([idx, int(truth), int(pred)])

    print("\nBest validation epoch:", best_epoch)
    print("Test accuracy:", f"{test_metrics['accuracy']:.6f}")
    print("Test macro-F1:", f"{test_metrics['macro_f1']:.6f}")
    print(
        "Clean false-positive rate:",
        f"{test_metrics['clean_false_positive_rate']:.6f}",
    )
    print("Confusion matrix:")
    for row in test_metrics["confusion_matrix"]:
        print(row)
    print("Results saved to:", run_dir)


if __name__ == "__main__":
    main()
