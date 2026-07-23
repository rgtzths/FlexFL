import types

import numpy as np
import pytest

tensorflow = pytest.importorskip("tensorflow")

import tensorflow as tf

from flexfl.ml_fw.TensorFlow import TensorFlow


def test_load_data_clamps_batch_size_to_n_samples():
    x = np.zeros((10, 3), dtype=np.float32)
    y = np.zeros((10,), dtype=np.int64)
    x_ds = tf.data.Dataset.from_tensor_slices(x)
    instance = object.__new__(TensorFlow)
    instance.batch_size = 2048
    instance.dataset = types.SimpleNamespace(
        load_data=lambda split, loader: (x_ds, y)
    )
    instance.load_data("train")
    assert instance.n_samples == 10
    assert instance.batch_size == 10
