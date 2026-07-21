import json

import pytest

from flexfl.neural_nets.Benchmark import Benchmark


DATA_CONFIG = {"n_layers": 2, "n_units_l0": 8, "n_units_l1": 4, "weight_decay": 0.01}
RESULTS_CONFIG = {"n_layers": 1, "n_units_l0": 16, "weight_decay": 0.02}


def _write_config(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f)


def test_load_prefers_shipped_data_config(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    configs_dir = tmp_path / "results/hyperparameter_optimization"
    monkeypatch.setattr("flexfl.neural_nets.Benchmark.DATA_DIR", data_dir)
    monkeypatch.setattr("flexfl.neural_nets.Benchmark.CONFIGS_DIR", configs_dir)

    _write_config(data_dir / "dummy" / "dummy.json", DATA_CONFIG)
    _write_config(configs_dir / "dummy.json", RESULTS_CONFIG)

    units, wd = Benchmark()._load("dummy")
    assert units == [8, 4]
    assert wd == 0.01


def test_load_falls_back_to_results_config(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    configs_dir = tmp_path / "results/hyperparameter_optimization"
    monkeypatch.setattr("flexfl.neural_nets.Benchmark.DATA_DIR", data_dir)
    monkeypatch.setattr("flexfl.neural_nets.Benchmark.CONFIGS_DIR", configs_dir)

    _write_config(configs_dir / "dummy.json", DATA_CONFIG)

    units, wd = Benchmark()._load("dummy")
    assert units == [8, 4]
    assert wd == 0.01


def test_load_resolves_config_cwd_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path / "data" / "dummy" / "dummy.json", DATA_CONFIG)

    units, wd = Benchmark()._load("dummy")
    assert units == [8, 4]
    assert wd == 0.01


def test_load_raises_when_neither_present(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    configs_dir = tmp_path / "results/hyperparameter_optimization"
    monkeypatch.setattr("flexfl.neural_nets.Benchmark.DATA_DIR", data_dir)
    monkeypatch.setattr("flexfl.neural_nets.Benchmark.CONFIGS_DIR", configs_dir)

    with pytest.raises(FileNotFoundError) as exc_info:
        Benchmark()._load("dummy")

    message = str(exc_info.value)
    assert str(data_dir / "dummy" / "dummy.json") in message
    assert str(configs_dir / "dummy.json") in message
