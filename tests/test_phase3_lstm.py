import torch

from flids.models.lstm import LSTMClassifier


def test_binary_lstm_forward_shape_and_deterministic_initialization():
    torch.manual_seed(17)
    first = LSTMClassifier(input_size=15, hidden_size=16, num_classes=2)
    torch.manual_seed(17)
    second = LSTMClassifier(input_size=15, hidden_size=16, num_classes=2)
    sample = torch.zeros(4, 30, 15)
    assert first(sample).shape == (4, 2)
    assert torch.equal(first(sample), second(sample))
