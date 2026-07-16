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


def test_get_device_respects_cuda_visible_devices_disabled(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    instance = object.__new__(PyTorch)
    device = instance.get_device()
    assert device.type == "cpu"
