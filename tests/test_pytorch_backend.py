import numpy as np
import pytest

torch = pytest.importorskip("torch")

from flexfl.ml_fw.PyTorch import PyTorch, LOSSES, _MAPE_EPSILON


def test_target_dtype_classification():
    assert PyTorch._target_dtype(True) is torch.long


def test_target_dtype_regression():
    assert PyTorch._target_dtype(False) is torch.float32


def test_align_for_loss_regression_reshapes_prediction():
    y_pred, y_true = PyTorch._align_for_loss(torch.zeros(4, 1), torch.zeros(4), False)
    assert y_pred.shape == (4,)
    assert y_true.shape == (4,)


def test_align_for_loss_classification_unchanged():
    y_pred, y_true = PyTorch._align_for_loss(torch.zeros(4, 3), torch.zeros(4), True)
    assert y_pred.shape == (4, 3)
    assert y_true.shape == (4,)


def test_mape_loss_zero_target_is_finite():
    mape = LOSSES['mape']()
    y_pred = torch.tensor([1.0, 2.0, 3.0])
    y_true = torch.tensor([0.0, 0.0, 0.0])
    result = mape(y_pred, y_true)
    assert torch.isfinite(result)


def test_mape_loss_known_value():
    mape = LOSSES['mape']()
    y_pred = torch.tensor([1.0, 2.0, 3.0])
    y_true = torch.tensor([2.0, 2.0, 6.0])
    result = mape(y_pred, y_true)
    expected = 100.0 * ((1.0 / 2.0) + (0.0 / 2.0) + (3.0 / 6.0)) / 3.0
    assert result.item() == pytest.approx(expected, rel=1e-5)


def test_mape_loss_matches_keras_scale():
    keras = pytest.importorskip("keras")
    y_pred = torch.tensor([1.0, 2.0, 3.0])
    y_true = torch.tensor([2.0, 2.0, 6.0])
    torch_mape = LOSSES['mape']()(y_pred, y_true).item()
    keras_mape = float(keras.losses.MeanAbsolutePercentageError()(
        np.array([2.0, 2.0, 6.0], dtype=np.float32),
        np.array([1.0, 2.0, 3.0], dtype=np.float32),
    ))
    assert torch_mape == pytest.approx(keras_mape, rel=1e-4)


def test_get_device_respects_cuda_visible_devices_disabled(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    instance = object.__new__(PyTorch)
    device = instance.get_device()
    assert device.type == "cpu"


def test_get_device_forces_cpu_even_when_cuda_available(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    instance = object.__new__(PyTorch)
    assert instance.get_device().type == "cpu"


def test_get_device_uses_cuda_when_available_and_not_disabled(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    instance = object.__new__(PyTorch)
    assert instance.get_device().type == "cuda"


def test_set_weights_guard_raises_on_wrong_length():
    instance = object.__new__(PyTorch)
    instance.model = torch.nn.Linear(2, 1)  # 2 weight + 1 bias = 3 params
    instance.device = torch.device("cpu")
    with pytest.raises(ValueError):
        instance.set_weights(np.zeros(5))


def test_set_weights_guard_accepts_correct_length():
    instance = object.__new__(PyTorch)
    instance.model = torch.nn.Linear(2, 1)
    instance.device = torch.device("cpu")
    instance.set_weights(np.zeros(3))
    assert instance.get_weights().size == 3
