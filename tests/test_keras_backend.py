import types

import numpy as np
import pytest

keras = pytest.importorskip("keras")
tf = pytest.importorskip("tensorflow")

from flexfl.ml_fw.Keras import Keras


def test_load_data_clamps_batch_size_to_n_samples():
    x = np.zeros((10, 3), dtype=np.float32)
    y = np.zeros((10,), dtype=np.int64)
    x_ds = tf.data.Dataset.from_tensor_slices(x)
    instance = object.__new__(Keras)
    instance.batch_size = 2048
    instance.dataset = types.SimpleNamespace(
        load_data=lambda split, loader: (x_ds, y)
    )
    instance.load_data("train")
    assert instance.n_samples == 10
    assert instance.batch_size == 10


def test_load_data_leaves_batch_size_unchanged_when_already_fits():
    x = np.zeros((10, 3), dtype=np.float32)
    y = np.zeros((10,), dtype=np.int64)
    x_ds = tf.data.Dataset.from_tensor_slices(x)
    instance = object.__new__(Keras)
    instance.batch_size = 2
    instance.dataset = types.SimpleNamespace(
        load_data=lambda split, loader: (x_ds, y)
    )
    instance.load_data("train")
    assert instance.batch_size == 2
    assert instance.n_samples // instance.batch_size >= 1


def test_set_seed_delegates_to_keras_set_random_seed(monkeypatch):
    calls = []
    monkeypatch.setattr(keras.utils, "set_random_seed", lambda seed: calls.append(seed))
    instance = object.__new__(Keras)
    instance.set_seed(1234)
    assert calls == [1234]
