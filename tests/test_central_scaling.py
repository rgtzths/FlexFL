import json

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

import flexfl.builtins.DatasetABC as DatasetABC_module
import flexfl.datasets.Benchmark as Benchmark_module
from flexfl.builtins.DatasetABC import DatasetABC
from flexfl.datasets.Benchmark import Benchmark
from flexfl.datasets.Housing import Housing
from flexfl.datasets.IOT_DNL import IOT_DNL
from flexfl.datasets.Slicing5g import Slicing5g
from flexfl.datasets.TON_IOT import TON_IOT
from flexfl.datasets.UNSW import UNSW

SCALING = "scaling.json"


class _Dataset(DatasetABC):

    @property
    def is_classification(self) -> bool:
        return True

    @property
    def scaler(self):
        return StandardScaler

    def download(self):
        pass

    def preprocess(self, val_size, test_size):
        pass


def _isolate(monkeypatch, tmp_path):
    metadata_dir = tmp_path / "_metadata"
    metadata_dir.mkdir()
    monkeypatch.setattr(DatasetABC_module, "DATA_FOLDER", str(tmp_path / "data"))
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))


def _raw(n=200):
    rng = np.random.default_rng(0)
    x = np.column_stack(
        [
            rng.normal(12000.0, 3000.0, n),
            rng.normal(0.5, 0.1, n),
            np.full(n, 7.0),
        ]
    )
    y = np.arange(n) % 2
    return x, y


def _cache(tmp_path, ds):
    return tmp_path / "data" / ds.name / "_data"


def _train_stats(raw_train):
    mean = raw_train.mean(axis=0)
    scale = raw_train.std(axis=0)
    scale[scale == 0] = 1.0
    return mean, scale


def test_split_save_scales_every_split_with_train_statistics(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw()
    ds.split_save(x, y, 0.2, 0.2)
    raw_train, _, raw_val, _, raw_test, _ = ds.split_data(x, y, 0.2, 0.2)
    mean, scale = _train_stats(raw_train)
    cache = _cache(tmp_path, ds)
    for name, raw in (("train", raw_train), ("val", raw_val), ("test", raw_test)):
        saved = np.load(cache / f"x_{name}.npy")
        np.testing.assert_allclose(saved, (raw - mean) / scale)
    train = np.load(cache / "x_train.npy")
    np.testing.assert_allclose(train[:, :2].mean(axis=0), 0.0, atol=1e-9)
    np.testing.assert_allclose(train[:, :2].std(axis=0), 1.0)
    assert np.all(train[:, 2] == 0.0)


def test_split_save_writes_the_fitted_statistics(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw()
    ds.split_save(x, y, 0.2, 0.2)
    raw_train, _, raw_val, _, _, _ = ds.split_data(x, y, 0.2, 0.2)
    mean, scale = _train_stats(raw_train)
    cache = _cache(tmp_path, ds)
    stats = json.loads((cache / SCALING).read_text())
    assert stats["scaler"] == "StandardScaler"
    assert stats["fitted_on"] == "train"
    assert stats["n_samples"] == raw_train.shape[0] == 120
    np.testing.assert_allclose(stats["mean"], mean)
    np.testing.assert_allclose(stats["scale"], scale)
    np.testing.assert_allclose(
        (raw_val - np.array(stats["mean"])) / np.array(stats["scale"]),
        np.load(cache / "x_val.npy"),
    )


def test_validation_and_test_rows_do_not_move_the_fit(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    x, y = _raw()
    first = _Dataset(data_name="first")
    first.split_save(x, y, 0.2, 0.2)
    raw_train = first.split_data(x, y, 0.2, 0.2)[0]
    holdout = ~np.isin(x[:, 1], raw_train[:, 1])
    assert holdout.sum() == 80
    shifted = x.copy()
    shifted[holdout] += 1.0e6
    second = _Dataset(data_name="second")
    second.split_save(shifted, y, 0.2, 0.2)
    first_train = np.load(_cache(tmp_path, first) / "x_train.npy")
    assert np.abs(first_train).max() < 10
    assert np.array_equal(
        first_train, np.load(_cache(tmp_path, second) / "x_train.npy")
    )


def test_interrupted_rebuild_leaves_no_statistics_file(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw()
    ds.split_save(x, y, 0.2, 0.2)
    save_data = ds.save_data

    def failing_save(xs, ys, split):
        if split == "val":
            raise OSError("disk full")
        save_data(xs, ys, split)

    ds.save_data = failing_save
    with pytest.raises(OSError, match="disk full"):
        ds.split_save(x * 2.0, y, 0.2, 0.2)
    del ds.save_data
    assert not (_cache(tmp_path, ds) / SCALING).exists()
    with pytest.raises(FileNotFoundError, match="flexfl-preprocess"):
        ds.data_division(num_workers=2, distribution="iid")


@pytest.mark.parametrize("distribution", ("iid", "non_iid", "dirichlet"))
def test_division_partitions_scaled_data_without_rescaling(
    monkeypatch, tmp_path, distribution
):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw(400)
    ds.split_save(x, y, 0.2, 0.2)
    cache = _cache(tmp_path, ds)
    train = np.load(cache / "x_train.npy")
    ds.data_division(num_workers=4, distribution=distribution)
    nodes = [
        np.load(tmp_path / "data" / ds.name / f"node_{i}" / "x_train.npy")
        for i in range(1, 5)
    ]
    rows = {tuple(r) for r in np.concatenate(nodes)}
    assert rows and rows <= {tuple(r) for r in train}
    assert np.array_equal(
        np.load(tmp_path / "data" / ds.name / "node_0" / "x_val.npy"),
        np.load(cache / "x_val.npy"),
    )


def test_iid_division_keeps_the_scaled_rows_in_order(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw(400)
    ds.split_save(x, y, 0.2, 0.2)
    ds.data_division(num_workers=4, distribution="iid")
    nodes = [
        np.load(tmp_path / "data" / ds.name / f"node_{i}" / "x_train.npy")
        for i in range(1, 5)
    ]
    assert np.array_equal(
        np.concatenate(nodes), np.load(_cache(tmp_path, ds) / "x_train.npy")
    )


def test_division_worker_saves_holdouts_without_rescaling(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw()
    ds.division_worker(x, y, 1, 0.2, 0.2)
    expected = ds.split_data(x, y, 0.2, 0.2)
    node = tmp_path / "data" / ds.name / "node_1"
    for i, name in enumerate(("train", "val", "test")):
        assert np.array_equal(np.load(node / f"x_{name}.npy"), expected[2 * i])
        assert np.array_equal(np.load(node / f"y_{name}.npy"), expected[2 * i + 1])


def test_division_refuses_a_cache_without_scaling_statistics(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw()
    x_train, y_train, x_val, y_val, _, _ = ds.split_data(x, y, 0.2, 0.2)
    ds.save_data(x_train, y_train, "train")
    ds.save_data(x_val, y_val, "val")
    with pytest.raises(FileNotFoundError, match="flexfl-preprocess"):
        ds.data_division(num_workers=2, distribution="iid")
    assert not (tmp_path / "data" / ds.name / "node_0").exists()


@pytest.mark.parametrize("cls", (Benchmark, Housing, IOT_DNL, Slicing5g, TON_IOT, UNSW))
def test_every_dataset_scales_with_standard_scaler(cls):
    assert cls.scaler.fget(object.__new__(cls)) is StandardScaler


def test_benchmark_preprocess_saves_standardized_splits(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    x, y = _raw(300)
    frame = pd.DataFrame(x, columns=["a", "b", "c"]).assign(
        label=np.where(y == 1, "yes", "no")
    )

    class _Hub:
        def to_pandas(self):
            return frame.copy()

    monkeypatch.setattr(
        Benchmark_module, "load_dataset", lambda *a, **kw: {"train": _Hub()}
    )
    ds = Benchmark(data_name="clf_num_synthetic")
    ds.preprocess(0.2, 0.2)
    cache = tmp_path / "data" / "clf_num_synthetic" / "_data"
    train = np.load(cache / "x_train.npy")
    assert np.abs(train).max() < 10
    np.testing.assert_allclose(train[:, :2].std(axis=0), 1.0)
    assert (cache / SCALING).is_file()
