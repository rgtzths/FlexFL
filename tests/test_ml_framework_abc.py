import pytest

from flexfl.builtins.MLFrameworkABC import MLFrameworkABC


def test_check_flat_length_raises_on_mismatch():
    with pytest.raises(ValueError):
        MLFrameworkABC._check_flat_length(10, 5, "set_weights")


def test_check_flat_length_returns_none_on_match():
    assert MLFrameworkABC._check_flat_length(10, 10, "set_weights") is None
