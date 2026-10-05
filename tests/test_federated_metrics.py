import numpy as np
import pytest

from flexfl.builtins.FederatedABC import FederatedABC, smape


def test_smape_matches_elementwise_for_column_preds():
    rng = np.random.default_rng(0)
    y = rng.uniform(1.0, 10.0, size=500)
    preds = y + rng.normal(0.0, 0.5, size=500)

    assert smape(y, preds.reshape(-1, 1)) == pytest.approx(smape(y, preds))


def test_smape_does_not_broadcast_to_a_matrix():
    y = np.array([1.0, 2.0, 3.0])
    preds = np.array([[1.0], [2.0], [3.0]])

    assert smape(y, preds) == pytest.approx(0.0)


def test_smape_zero_denominator_contributes_zero():
    y = np.array([0.0, 4.0])
    preds = np.array([[0.0], [4.0]])

    assert smape(y, preds) == pytest.approx(0.0)


class _Dataset:
    is_classification = False

    @staticmethod
    def unscale_target(values, target):
        return np.asarray(values, dtype=float) * target["scale"] + target["mean"]


class _ML:
    def __init__(self, y, preds):
        self.y_val = y
        self.x_val = np.zeros((len(y), 1))
        self._preds = preds
        self.dataset = _Dataset()

    def predict(self, x):
        return self._preds

    def calculate_loss(self, y_true, y_pred):
        return 0.0

    def get_weights(self):
        return None


class _Federated(FederatedABC):
    def setup(self):
        pass

    def master_loop(self):
        pass

    def get_worker_info(self):
        return {}


def _federated_for(y, preds):
    f = _Federated.__new__(_Federated)
    f.ml = _ML(y, preds)
    f.is_classification = False
    f.metrics = ["mape"]
    f.epochs = 1
    f.epoch_start = 0.0
    f.best_score = None
    f.best_weights = None
    return f


def test_validate_normalises_column_predictions():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    preds = np.array([[1.5], [2.5], [3.5], [4.5]])

    f = _federated_for(y, preds)
    f.validate(epoch=1)

    assert f.new_score == pytest.approx(smape(y, preds.ravel()))


def test_validate_rejects_shape_mismatch():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    preds = np.array([[1.5], [2.5]])

    f = _federated_for(y, preds)
    with pytest.raises(ValueError):
        f.validate(epoch=1)


def test_validate_destandardizes_regression_predictions():
    y = np.array([95.0, 100.0, 110.0])
    f = _federated_for(y, np.array([[-0.5], [0.0], [1.0]]))
    f.target_stats = {"mean": 100.0, "scale": 10.0}
    received = []

    def calculate_loss(labels, predictions):
        received.append((labels.copy(), predictions.copy()))
        return float(np.mean((labels - predictions.ravel()) ** 2))

    f.ml.calculate_loss = calculate_loss
    f.validate(epoch=1)
    assert f.new_score == pytest.approx(0.0)
    assert f.new_loss == pytest.approx(0.0)
    assert len(received) == 1
    np.testing.assert_array_equal(received[0][0], y)
    np.testing.assert_array_equal(received[0][1], [[95.0], [100.0], [110.0]])


def test_validate_leaves_predictions_without_target_stats():
    assert FederatedABC.target_stats is None
    y = np.array([95.0, 100.0, 110.0])
    preds = np.array([[94.0], [102.0], [108.0]])
    f = _federated_for(y, preds)
    f.validate(epoch=1)
    assert f.new_score == pytest.approx(smape(y, preds))
