import pytest

torch = pytest.importorskip("torch")

from flids.models.lstm import LSTMClassifier, save_checkpoint


def test_binary_lstm_forward_shape_and_deterministic_initialization():
    torch.manual_seed(17)
    first = LSTMClassifier(input_size=15, hidden_size=16, num_classes=2)
    torch.manual_seed(17)
    second = LSTMClassifier(input_size=15, hidden_size=16, num_classes=2)
    sample = torch.zeros(4, 30, 15)
    assert first(sample).shape == (4, 2)
    assert torch.equal(first(sample), second(sample))


def test_checkpoint_round_trip(tmp_path):
    torch.manual_seed(19)
    model = LSTMClassifier(input_size=15, hidden_size=8, num_classes=2)
    target = tmp_path / "model_state.pt"
    save_checkpoint(model, target)
    restored = LSTMClassifier(input_size=15, hidden_size=8, num_classes=2)
    restored.load_state_dict(torch.load(target, map_location="cpu", weights_only=True))
    sample = torch.randn(2, 30, 15)
    model.eval()
    restored.eval()
    assert torch.equal(model(sample), restored(sample))
