import pytest

from flexfl.builtins.MLFrameworkABC import MLFrameworkABC

from conftest import _FakeML


def test_clamp_reduces_batch_size_to_n_samples():
    instance = object.__new__(_FakeML)
    instance.batch_size = 2048
    instance._set_n_samples_and_clamp_batch_size(60)
    assert instance.n_samples == 60
    assert instance.batch_size == 60


def test_clamp_leaves_batch_size_when_below_n_samples():
    instance = object.__new__(_FakeML)
    instance.batch_size = 32
    instance._set_n_samples_and_clamp_batch_size(1000)
    assert instance.n_samples == 1000
    assert instance.batch_size == 32


def test_clamp_raises_when_n_samples_zero():
    instance = object.__new__(_FakeML)
    instance.batch_size = 32
    with pytest.raises(ValueError):
        instance._set_n_samples_and_clamp_batch_size(0)


def test_check_flat_length_raises_on_mismatch():
    with pytest.raises(ValueError):
        MLFrameworkABC._check_flat_length(10, 5, "set_weights")


def test_check_flat_length_raises_on_too_long():
    with pytest.raises(ValueError):
        MLFrameworkABC._check_flat_length(5, 10, "set_weights")


def test_check_flat_length_returns_none_on_match():
    assert MLFrameworkABC._check_flat_length(10, 10, "set_weights") is None
