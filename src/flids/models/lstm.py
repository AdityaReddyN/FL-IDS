from __future__ import annotations

from pathlib import Path

import torch
from torch import nn


class LSTMClassifier(nn.Module):
    """Small sequence classifier for the 30-step v3 window representation."""

    def __init__(self, input_size: int, hidden_size: int = 32, num_classes: int = 2) -> None:
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.classifier = nn.Linear(hidden_size, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.lstm(x)
        return self.classifier(hidden[-1])


def save_checkpoint(model: nn.Module, path: str | Path) -> None:
    """Save CPU-portable model weights without optimizer or training data."""
    torch.save({key: value.detach().cpu() for key, value in model.state_dict().items()}, path)
