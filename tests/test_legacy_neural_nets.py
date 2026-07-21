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
    # Behavioral proof (survives a softmax applied outside an nn.Softmax module):
    # a logits tensor is not a probability simplex, so its rows do not sum to 1.
    torch.manual_seed(0)
    out = model(torch.randn(BATCH, *INPUT_SHAPE))
    assert not torch.allclose(out.sum(dim=1), torch.ones(BATCH), atol=1e-5)


def _discover_neural_nets():
    import importlib
    import pkgutil

    import flexfl.neural_nets as nn_pkg
    from flexfl.builtins.NeuralNetworkABC import NeuralNetworkABC

    found = set()
    for mod in pkgutil.iter_modules(nn_pkg.__path__):
        module = importlib.import_module(f"flexfl.neural_nets.{mod.name}")
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, NeuralNetworkABC)
                and obj is not NeuralNetworkABC
            ):
                found.add(obj)
    return found


def test_all_neural_nets_guarded_against_torch_softmax():
    # Every NeuralNetworkABC subclass must be covered by the logits guard above,
    # so a new net cannot silently re-introduce the torch double-softmax bug.
    # Pure import + subclass check, so it runs without any ML backend installed.
    discovered = _discover_neural_nets()
    uncovered = discovered ^ set(CLASSIFICATION_NETS)
    assert discovered == set(CLASSIFICATION_NETS), (
        "NeuralNetworkABC subclass(es) not covered by "
        "test_torch_classification_model_outputs_logits: "
        f"{sorted(c.__name__ for c in uncovered)}. Add each to CLASSIFICATION_NETS."
    )
