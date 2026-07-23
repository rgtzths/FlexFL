from types import SimpleNamespace

import numpy as np
import pytest

keras = pytest.importorskip("keras")
tensorflow = pytest.importorskip("tensorflow")

import tensorflow as tf

from flexfl.ml_fw.Keras import Keras
from flexfl.fl_algos.CentralizedSync import CentralizedSync
from flexfl.fl_algos.CentralizedAsync import CentralizedAsync


def _make_worker_algo(algo_cls):
    x = np.zeros((10, 3), dtype=np.float32)
    y = np.zeros((10,), dtype=np.int64)
    x_ds = tf.data.Dataset.from_tensor_slices(x)
    algo_instance = object.__new__(algo_cls)
    algo_instance.is_master = False
    algo_instance.wm = SimpleNamespace(set_callbacks=lambda *a, **k: None)
    algo_instance.ml = object.__new__(Keras)
    algo_instance.ml.batch_size = 2048
    algo_instance.ml.dataset = SimpleNamespace(
        load_data=lambda split, loader: (x_ds, y)
    )
    return algo_instance


@pytest.mark.parametrize("algo_cls", [CentralizedSync, CentralizedAsync])
def test_worker_reports_at_least_one_batch(algo_cls):
    algo_instance = _make_worker_algo(algo_cls)
    algo_instance.setup()
    info = algo_instance.get_worker_info()
    assert info["n_batches"] >= 1
