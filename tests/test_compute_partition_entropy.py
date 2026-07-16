import numpy as np
import pytest

from compute_partition_entropy import numeric_columns, per_feature_split_entropy, summarize


def test_per_feature_split_entropy_even_split_near_one():
    rng = np.random.default_rng(0)
    worker_a = rng.uniform(0, 1, size=(200, 1))
    worker_b = rng.uniform(0, 1, size=(200, 1))

    entropies = per_feature_split_entropy([worker_a, worker_b], n_bins=10)

    assert len(entropies) == 1
    assert entropies[0] == pytest.approx(1.0, abs=0.05)


def test_per_feature_split_entropy_concentrated_split_near_zero():
    worker_a = np.linspace(0.0, 1.0, 200).reshape(-1, 1)
    worker_b = np.full((200, 1), 5.0)

    entropies = per_feature_split_entropy([worker_a, worker_b], n_bins=10)

    assert len(entropies) == 1
    assert entropies[0] < 0.2


def test_per_feature_split_entropy_fewer_than_two_workers_returns_empty():
    worker_a = np.zeros((10, 1))
    assert per_feature_split_entropy([worker_a], n_bins=10) == []


def test_per_feature_split_entropy_constant_feature_skipped():
    worker_a = np.ones((10, 1))
    worker_b = np.ones((10, 1))

    entropies = per_feature_split_entropy([worker_a, worker_b], n_bins=10)

    assert entropies == []


def test_summarize_empty_gives_none_fields_and_zero_features_used():
    result = summarize([], n_bins=10)

    assert result["mean"] is None
    assert result["min"] is None
    assert result["max"] is None
    assert result["std"] is None
    assert result["n_features_used"] == 0


def test_summarize_nonempty():
    result = summarize([0.2, 0.4, 0.6], n_bins=10)

    assert result["n_features_used"] == 3
    assert result["min"] == 0.2
    assert result["max"] == 0.6


def test_numeric_columns_drops_string_columns():
    arr = np.array([
        ["1.0", "a"],
        ["2.0", "b"],
    ], dtype=object)

    assert numeric_columns(arr) == [0]
