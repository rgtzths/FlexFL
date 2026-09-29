import sys

from flexfl.cli import fl


class _Component:
    created = []

    def __init__(self, **kwargs):
        _Component.created.append(kwargs)

    def run(self):
        pass


def test_a_later_epochs_flag_overrides_the_sampled_cap(monkeypatch):
    for var in ("KERAS_BACKEND", "CUDA_VISIBLE_DEVICES", "TF_CPP_MIN_LOG_LEVEL"):
        monkeypatch.setenv(var, "")
    monkeypatch.setattr(fl, "load_class", lambda path: _Component)
    monkeypatch.setattr(sys, "argv", [
        "flexfl", "--fl", "cs", "--dataset", "Benchmark", "--nn", "benchmark",
        "--epochs", "200", "--epochs", "7",
    ])
    _Component.created.clear()
    fl.main()
    assert _Component.created[-1]["epochs"] == 7
    assert _Component.created[-1]["all_args"]["epochs"] == 7
