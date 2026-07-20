import numpy as np
import pytest

from flexfl.neural_nets.IOT_DNL import IOT_DNL
from flexfl.neural_nets.TON_IOT import TON_IOT
from flexfl.neural_nets.UNSW import UNSW
from flexfl.neural_nets.Slicing5g import Slicing5g
from flexfl.neural_nets.Benchmark import Benchmark


INPUT_SHAPE = (10,)
OUTPUT_SIZE = 4
BATCH = 3

CLASSES = [TON_IOT, UNSW, Slicing5g]

CLASSIFICATION_NETS = [IOT_DNL, Benchmark, TON_IOT, UNSW, Slicing5g]


@pytest.mark.parametrize("nn_cls", CLASSES, ids=lambda c: c.__name__)
def test_keras_model_forward_pass_shape(nn_cls):
    pytest.importorskip("keras")
    instance = nn_cls()
    model = instance.keras_model("dummy", INPUT_SHAPE, OUTPUT_SIZE, True)
    x = np.random.randn(BATCH, *INPUT_SHAPE).astype("float32")
    output = model(x)
    assert tuple(output.shape) == (BATCH, OUTPUT_SIZE)


@pytest.mark.parametrize("nn_cls", CLASSES, ids=lambda c: c.__name__)
def test_tf_model_forward_pass_shape(nn_cls):
    tf = pytest.importorskip("tensorflow")
    instance = nn_cls()
    model = instance.tf_model("dummy", INPUT_SHAPE, OUTPUT_SIZE, True)
    x = tf.random.normal((BATCH, *INPUT_SHAPE))
    output = model(x)
    assert tuple(output.shape) == (BATCH, OUTPUT_SIZE)


@pytest.mark.parametrize("nn_cls", CLASSES, ids=lambda c: c.__name__)
def test_torch_model_forward_pass_shape(nn_cls):
    torch = pytest.importorskip("torch")
    instance = nn_cls()
    model = instance.torch_model("dummy", INPUT_SHAPE, OUTPUT_SIZE, True)
    x = torch.randn(BATCH, *INPUT_SHAPE)
    output = model(x)
    assert tuple(output.shape) == (BATCH, OUTPUT_SIZE)


@pytest.mark.parametrize("nn_cls", CLASSIFICATION_NETS, ids=lambda c: c.__name__)
def test_torch_classification_model_outputs_logits(nn_cls, monkeypatch):
    torch = pytest.importorskip("torch")
    import torch.nn as nn
    if nn_cls is Benchmark:
        # Benchmark's real _load reads a gitignored HPO config file; stub it to
        # a fixed (units, weight_decay) architecture.
        monkeypatch.setattr(Benchmark, "_load", lambda self, data_name: ([8], 0.0))
    model = nn_cls().torch_model("dummy", INPUT_SHAPE, OUTPUT_SIZE, True)
    assert not any(isinstance(m, nn.Softmax) for m in model.modules())
