import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

import flexfl.builtins.DatasetABC as dataset_module
from flexfl.builtins.FederatedABC import smape
from flexfl.datasets.Benchmark import Benchmark

tf = pytest.importorskip("tensorflow")


@pytest.fixture
def model_finder(monkeypatch, tmp_path):
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    monkeypatch.setattr(dataset_module, "METADATA_FOLDER", metadata)
    monkeypatch.setattr(dataset_module, "DATA_FOLDER", str(tmp_path / "data"))
    path = Path(__file__).resolve().parents[1] / "src" / "other" / "model_finder.py"
    spec = importlib.util.spec_from_file_location("model_finder_t069", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_cache(ds, *, with_target=True):
    y_train = np.array([80.0, 90.0, 110.0, 120.0])
    y_val = np.array([96.0, 103.0, 112.0])
    ds.save_data(np.arange(4, dtype=float).reshape(-1, 1), y_train, "train")
    ds.save_data(np.array([[-0.5], [0.0], [1.0]]), y_val, "val")
    target = {
        "fitted_on": "train",
        "n_samples": 4,
        "mean": float(y_train.mean()),
        "scale": float(y_train.std()),
    }
    stats = {"scaler": "StandardScaler"}
    if with_target:
        stats["target"] = target
    (Path(ds.data_path) / "scaling.json").write_text(json.dumps(stats))
    return y_train, y_val, target


def _labels(dataset):
    return np.concatenate([labels.numpy() for _, labels in dataset])


@pytest.mark.parametrize("data_folder", (None, "node_1"))
def test_get_dataset_standardizes_train_and_keeps_raw_validation(
    model_finder, monkeypatch, data_folder
):
    ds = Benchmark(data_name="reg_num_synthetic", data_folder="_data")
    y_train, y_val, target = _write_cache(ds)
    if data_folder is not None:
        monkeypatch.setenv("DATA_FOLDER", data_folder)
        node = Benchmark(data_name=ds.name, data_folder=data_folder)
        _write_cache(node)
    result = model_finder.get_dataset(ds.name)
    train_y = _labels(result[0])
    np.testing.assert_allclose(train_y.mean(), 0.0, atol=1e-7)
    np.testing.assert_allclose(train_y.std(), 1.0, atol=1e-7)
    np.testing.assert_allclose(
        np.sort(train_y), np.sort((y_train - target["mean"]) / target["scale"])
    )
    assert train_y.dtype == np.float32
    np.testing.assert_array_equal(np.sort(_labels(result[1])), np.sort(y_val))
    assert len(result) == 4
    assert result[2] == 1
    assert result[3] == target


def test_get_dataset_rebuilds_a_cache_without_target_statistics(
    model_finder, monkeypatch
):
    ds = Benchmark(data_name="reg_num_synthetic", data_folder="_data")
    _write_cache(ds, with_target=False)
    calls = []

    def preprocess(dataset, val_size, test_size):
        calls.append((dataset.data_path, val_size, test_size))
        _write_cache(dataset)

    monkeypatch.setattr(Benchmark, "preprocess", preprocess)
    result = model_finder.get_dataset(ds.name)
    assert calls == [(ds.default_folder, 0.15, 0.15)]
    labels = _labels(result[0])
    np.testing.assert_allclose(labels.mean(), 0.0, atol=1e-7)
    np.testing.assert_allclose(labels.std(), 1.0, atol=1e-7)
    assert len(result) == 4
    assert result[3]["mean"] == 100.0


def test_objective_scores_regression_smape_in_original_units(model_finder, monkeypatch):
    ds = Benchmark(data_name="reg_num_synthetic", data_folder="_data")
    _, y_val, target = _write_cache(ds)
    monkeypatch.setattr(model_finder, "BATCHSIZE", 2)

    def model(samples, training=False):
        assert training is False
        return tf.cast(samples[:, :1], tf.float32)

    monkeypatch.setattr(model_finder, "create_model", lambda trial, classes: model)
    monkeypatch.setattr(model_finder, "create_optimizer", lambda trial: Mock())
    score = model_finder.objective(model_finder.optuna.trial.FixedTrial({}), ds.name, 0)
    predictions = np.array([-0.5, 0.0, 1.0]) * target["scale"] + target["mean"]
    assert float(score) == pytest.approx(smape(y_val, predictions))
