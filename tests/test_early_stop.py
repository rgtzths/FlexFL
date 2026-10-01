import math
import random
from collections import deque
from pathlib import Path

import numpy as np
import pytest

import flexfl.builtins.FederatedABC as federated_module
from flexfl.builtins.FederatedABC import FederatedABC
from flexfl.cli.utils import get_args_from_file


class _Federated(FederatedABC):
    def setup(self):
        pass

    def master_loop(self):
        pass

    def get_worker_info(self):
        return {}


def _federated(
    *,
    classification=True,
    patience=4,
    delta=0.01,
    early_stop_on="loss",
    min_epochs=10,
    target_score=None,
):
    f = _Federated.__new__(_Federated)
    f.is_classification = classification
    f.patience = patience
    f.delta = delta
    f.early_stop_on = early_stop_on
    f.min_epochs = min_epochs
    f.target_score = (
        target_score if target_score is not None else (1.0 if classification else 0.0)
    )
    f.buffer = deque(maxlen=patience)
    f.compare_score = None
    f.last_epoch = None
    return f


def _stop_epoch(f, losses, scores=None):
    scores = scores or [0.0] * len(losses)
    for epoch, (loss, score) in enumerate(zip(losses, scores), start=1):
        f.new_loss, f.new_score, f.last_epoch = loss, score, epoch
        if f.early_stop():
            return epoch
    return None


def _old_stop_epoch(scores, classification, patience, delta, target_score):
    buffer, compare_score = deque(maxlen=patience), None
    for epoch, new_score in enumerate(scores, start=1):
        if (classification and new_score >= target_score) or (
            not classification and new_score <= target_score
        ):
            return epoch
        if len(buffer) < patience:
            buffer.append(new_score)
            continue
        old_score = buffer.popleft()
        if (
            compare_score is None
            or (classification and old_score > compare_score)
            or (not classification and old_score < compare_score)
        ):
            compare_score = old_score
        buffer.append(new_score)
        if classification and not any(s >= compare_score + delta for s in buffer):
            return epoch
        if not classification and not any(s <= compare_score - delta for s in buffer):
            return epoch
    return None


def test_flat_metric_with_falling_loss_does_not_stop():
    f = _federated(patience=4, delta=0.01)
    assert _stop_epoch(f, [0.6931 * 0.98**e for e in range(60)]) is None


@pytest.mark.parametrize("patience, expected", [(4, 10), (9, 10), (12, 13)])
def test_flat_loss_stops_at_the_later_of_the_floor_and_patience_plus_one(
    patience, expected
):
    f = _federated(patience=patience, delta=0.01)
    assert _stop_epoch(f, [0.69] * 40) == expected


def test_floor_zero_lets_a_flat_loss_stop_at_patience_plus_one():
    f = _federated(patience=4, delta=0.01, min_epochs=0)
    assert _stop_epoch(f, [0.69] * 40) == 5


def test_flat_metric_under_the_metric_rule_stops_at_the_floor():
    f = _federated(patience=4, delta=0.01, early_stop_on="metric")
    assert _stop_epoch(f, [0.69] * 40, [0.0] * 40) == 10


@pytest.mark.parametrize("scale", [1.0, 1e-3, 1e3])
def test_the_loss_rule_is_scale_free(scale):
    curve = [
        1.0,
        0.9,
        0.85,
        0.84,
        0.838,
        0.837,
        0.8369,
        0.8368,
        0.8367,
        0.8366,
        0.8365,
        0.8364,
        0.8363,
    ]
    f = _federated(patience=3, delta=0.01, min_epochs=0)
    assert _stop_epoch(f, [v * scale for v in curve]) == 7


def test_improvement_below_the_relative_delta_counts_as_a_stall():
    f = _federated(patience=3, delta=0.01, min_epochs=0)
    assert _stop_epoch(f, [1.0, 0.995, 0.991, 0.9905]) == 4


def test_improvement_equal_to_the_relative_delta_counts_as_progress():
    f = _federated(patience=3, delta=0.01, min_epochs=0)
    assert _stop_epoch(f, [1.0, 0.995, 0.991, 0.99]) is None


def test_target_reached_before_the_floor_stops_at_the_floor():
    f = _federated(patience=4, delta=0.01)
    scores = [0.2, 0.5, 1.0] + [1.0] * 20
    assert _stop_epoch(f, [0.69 * 0.9**e for e in range(23)], scores) == 10


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_non_finite_loss_counts_as_no_improvement(bad):
    f = _federated(patience=4, delta=0.01)
    assert _stop_epoch(f, [bad] * 20) == 10


def test_a_finite_loss_after_non_finite_ones_is_an_improvement():
    f = _federated(patience=3, delta=0.01)
    losses = [math.nan] * 3 + [0.69 * 0.95**e for e in range(30)]
    assert _stop_epoch(f, losses) is None


@pytest.mark.parametrize("classification", [True, False])
@pytest.mark.parametrize("seed", range(40))
def test_metric_rule_with_no_floor_matches_the_previous_rule(classification, seed):
    rng = random.Random(seed)
    patience = rng.randint(3, 10)
    delta = round(10 ** rng.uniform(-3, math.log10(5e-2)), 5)
    target = 1.0 if classification else 0.0
    scores = [
        round(rng.uniform(0.0, 1.0 if classification else 3.0), 3) for _ in range(40)
    ]
    if seed % 5 == 0:
        scores[rng.randint(0, 39)] = target
    f = _federated(
        classification=classification,
        patience=patience,
        delta=delta,
        early_stop_on="metric",
        min_epochs=0,
        target_score=target,
    )
    assert _stop_epoch(f, [0.5] * 40, scores) == _old_stop_epoch(
        scores, classification, patience, delta, target
    )


@pytest.mark.parametrize(
    "scores",
    [
        [math.inf] * 20,
        [2.0, math.inf, math.inf, math.inf, math.inf, math.inf],
        [math.nan] * 20,
    ],
)
def test_metric_rule_with_no_floor_matches_the_previous_rule_on_non_finite_scores(
    scores,
):
    f = _federated(
        classification=False,
        patience=4,
        delta=0.01,
        early_stop_on="metric",
        min_epochs=0,
    )
    assert _stop_epoch(f, [0.5] * len(scores), scores) == _old_stop_epoch(
        scores, False, 4, 0.01, 0.0
    )


class _Dataset:
    is_classification = False


class _ML:
    def __init__(self, losses):
        self.y_val = np.array([1.0, 2.0])
        self.x_val = np.zeros((2, 1))
        self.dataset = _Dataset()
        self._losses = iter(losses)

    def predict(self, x):
        return np.array([[1.5], [2.5]])

    def calculate_loss(self, y_true, y_pred):
        return next(self._losses)

    def get_weights(self):
        return None


def _validating_federated(losses, **kwargs):
    f = _federated(classification=False, **kwargs)
    f.ml = _ML(losses)
    f.metrics = ["mape"]
    f.epochs = 200
    f.epoch_start = 0.0
    f.best_score = None
    f.best_weights = None
    return f


def test_validate_hands_its_loss_and_epoch_to_early_stop():
    f = _validating_federated([0.7, 0.6])
    f.validate(epoch=3)
    assert (f.new_loss, f.last_epoch) == (0.7, 3)
    f.validate(epoch=4)
    assert (f.new_loss, f.last_epoch) == (0.6, 4)


def test_real_validation_of_a_flat_loss_stops_at_the_floor():
    f = _validating_federated([0.69] * 30, patience=4, delta=0.01)
    stops = []
    for epoch in range(1, 31):
        f.validate(epoch=epoch)
        if f.early_stop():
            stops.append(epoch)
            break
    assert stops == [10]


def test_real_validation_reaching_the_target_waits_for_the_floor():
    f = _validating_federated(
        [0.69 * 0.9**e for e in range(30)], patience=4, delta=0.01, target_score=1.0
    )
    stops = []
    for epoch in range(1, 31):
        f.validate(epoch=epoch)
        if f.early_stop():
            stops.append(epoch)
            break
    assert stops == [10]


def _constructed(monkeypatch, **kwargs):
    for name in ("setup_metrics", "setup_nodes", "setup_failure"):
        monkeypatch.setattr(FederatedABC, name, lambda self: None)
    return _Federated(ml=None, wm=None, all_args={}, **kwargs)


def test_constructor_defaults_to_the_loss_rule_with_a_floor_of_10(monkeypatch):
    f = _constructed(monkeypatch)
    assert (f.early_stop_on, f.min_epochs, f.new_loss, f.last_epoch) == (
        "loss",
        10,
        None,
        None,
    )


def test_constructor_keeps_explicit_rule_arguments(monkeypatch):
    f = _constructed(monkeypatch, early_stop_on="metric", min_epochs=0)
    assert (f.early_stop_on, f.min_epochs) == ("metric", 0)


@pytest.mark.parametrize("kwargs", [{"early_stop_on": "mcc"}, {"min_epochs": -1}])
def test_constructor_rejects_invalid_rule_arguments(monkeypatch, kwargs):
    with pytest.raises(AssertionError):
        _constructed(monkeypatch, **kwargs)


def test_rule_arguments_are_cli_flags():
    args = get_args_from_file(str(Path(federated_module.__file__)))
    assert (args["early_stop_on"], args["min_epochs"]) == ((str, "loss"), (int, 10))


@pytest.mark.parametrize(
    "early_stop_on, min_epochs",
    [("mcc", 10), ("loss", -1), ("loss", 2.5), ("loss", True)],
)
def test_invalid_early_stop_args_are_rejected(early_stop_on, min_epochs):
    f = _federated(early_stop_on=early_stop_on, min_epochs=min_epochs)
    with pytest.raises(AssertionError):
        f.check_early_stop_args()


@pytest.mark.parametrize("early_stop_on, min_epochs", [("loss", 10), ("metric", 0)])
def test_valid_early_stop_args_are_accepted(early_stop_on, min_epochs):
    _federated(
        early_stop_on=early_stop_on, min_epochs=min_epochs
    ).check_early_stop_args()
