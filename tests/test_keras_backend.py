import pytest

keras = pytest.importorskip("keras")

from flexfl.ml_fw.Keras import Keras


def test_set_seed_delegates_to_keras_set_random_seed(monkeypatch):
    calls = []
    monkeypatch.setattr(keras.utils, "set_random_seed", lambda seed: calls.append(seed))
    instance = object.__new__(Keras)
    instance.set_seed(1234)
    assert calls == [1234]
