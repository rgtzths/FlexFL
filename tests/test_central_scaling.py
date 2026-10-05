import json

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import MinMaxScaler, StandardScaler

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


class _Regression(_Dataset):

    @property
    def is_classification(self) -> bool:
        return False


def _regression_raw(n=403):
    x, _ = _raw(n)
    y = np.random.default_rng(42).normal(100.0, 12.0, n)
    return x, y


def _regression_cache(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Regression()
    x, y = _regression_raw()
    ds.split_save(x, y, 0.2, 0.2)
    return ds


def _raw_partitions(ds, distribution, workers=4):
    if distribution == "iid":
        return ds.division_iid(workers)
    if distribution == "non_iid":
        return ds.division_non_iid(workers, 0.9)
    return ds.division_non_iid_dirichlet(workers, 0.5)


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


def test_refused_division_keeps_the_previous_partitions(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw()
    ds.split_save(x, y, 0.2, 0.2)
    ds.data_division(num_workers=2, distribution="iid")
    node = tmp_path / "data" / ds.name / "node_1" / "x_train.npy"
    before = np.load(node)
    (_cache(tmp_path, ds) / SCALING).unlink()
    with pytest.raises(FileNotFoundError, match="flexfl-preprocess"):
        ds.data_division(num_workers=2, distribution="iid")
    assert np.array_equal(np.load(node), before)


def test_failed_statistics_write_leaves_no_marker(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw()
    ds.split_save(x, y, 0.2, 0.2)

    def failing_replace(src, dst):
        raise OSError("rename failed")

    monkeypatch.setattr(DatasetABC_module.os, "replace", failing_replace)
    with pytest.raises(OSError, match="rename failed"):
        ds.split_save(x * 2.0, y, 0.2, 0.2)
    assert sorted(p.name for p in _cache(tmp_path, ds).glob("scaling*")) == []


def test_failed_metadata_write_leaves_no_marker(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    x, y = _raw()
    ds.split_save(x, y, 0.2, 0.2)

    def failing_metadata():
        raise OSError("metadata write failed")

    ds.save_metadata = failing_metadata
    with pytest.raises(OSError, match="metadata write failed"):
        ds.split_save(x * 2.0, y, 0.2, 0.2)
    assert not (_cache(tmp_path, ds) / SCALING).exists()


def test_scaler_without_statistics_is_refused_before_saving(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    class _MinMax(_Dataset):
        @property
        def scaler(self):
            return MinMaxScaler

    ds = _MinMax()
    x, y = _raw()
    with pytest.raises(TypeError, match="MinMaxScaler"):
        ds.split_save(x, y, 0.2, 0.2)
    assert not _cache(tmp_path, ds).exists()


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


def test_regression_split_save_records_train_target_statistics(monkeypatch, tmp_path):
    ds = _regression_cache(monkeypatch, tmp_path)
    x, y = _regression_raw()
    raw = ds.split_data(x, y, 0.2, 0.2)
    cache = _cache(tmp_path, ds)
    stats = json.loads((cache / SCALING).read_text())
    assert "target" in stats
    assert stats["target"] == {
        "fitted_on": "train",
        "n_samples": len(raw[1]),
        "mean": pytest.approx(raw[1].mean()),
        "scale": pytest.approx(raw[1].std()),
    }
    for index, split in enumerate(("train", "val", "test")):
        np.testing.assert_array_equal(
            np.load(cache / f"y_{split}.npy"), raw[2 * index + 1]
        )


def test_classification_split_save_records_no_target(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Dataset()
    ds.split_save(*_raw(), 0.2, 0.2)
    stats = json.loads((_cache(tmp_path, ds) / SCALING).read_text())
    assert "target" in stats
    assert stats["target"] is None


@pytest.mark.parametrize("distribution", ("iid", "non_iid", "dirichlet"))
def test_regression_division_standardizes_worker_targets(
    monkeypatch, tmp_path, distribution
):
    ds = _regression_cache(monkeypatch, tmp_path)
    cache = _cache(tmp_path, ds)
    train_y = np.load(cache / "y_train.npy")
    raw_x, raw_y = _raw_partitions(ds, distribution)
    ds.data_division(num_workers=4, distribution=distribution)
    for worker in range(4):
        node = cache.parent / f"node_{worker + 1}"
        np.testing.assert_array_equal(np.load(node / "x_train.npy"), raw_x[worker])
        np.testing.assert_allclose(
            np.load(node / "y_train.npy"),
            (raw_y[worker] - train_y.mean()) / train_y.std(),
        )
    if distribution != "non_iid":
        assert {tuple(row) for row in np.concatenate(raw_x)} == {
            tuple(row) for row in np.load(cache / "x_train.npy")
        }
    else:
        assert sum(map(len, raw_y)) < len(train_y)
    np.testing.assert_array_equal(
        np.load(cache.parent / "node_0" / "y_val.npy"), np.load(cache / "y_val.npy")
    )


@pytest.mark.parametrize("distribution", ("iid", "non_iid", "dirichlet"))
def test_regression_partitions_match_raw_division(monkeypatch, tmp_path, distribution):
    ds = _regression_cache(monkeypatch, tmp_path)
    raw_x, _ = _raw_partitions(ds, distribution)
    ds.data_division(num_workers=4, distribution=distribution)
    for worker in range(4):
        np.testing.assert_array_equal(
            np.load(_cache(tmp_path, ds).parent / f"node_{worker + 1}" / "x_train.npy"),
            raw_x[worker],
        )


def test_regression_worker_holdouts_are_standardized(monkeypatch, tmp_path):
    ds = _regression_cache(monkeypatch, tmp_path)
    cache = _cache(tmp_path, ds)
    train_y = np.load(cache / "y_train.npy")
    raw_x, raw_y = ds.division_iid(2)
    ds.data_division(num_workers=2, val_size=0.2, test_size=0.2, distribution="iid")
    for worker in range(2):
        expected = ds.split_data(raw_x[worker], raw_y[worker], 0.2, 0.2)
        for index, split in enumerate(("train", "val", "test")):
            node = cache.parent / f"node_{worker + 1}"
            np.testing.assert_array_equal(
                np.load(node / f"x_{split}.npy"), expected[2 * index]
            )
            np.testing.assert_allclose(
                np.load(node / f"y_{split}.npy"),
                (expected[2 * index + 1] - train_y.mean()) / train_y.std(),
            )


@pytest.mark.parametrize("target", ({}, {"mean": 1.0, "scale": 0.0}, None))
def test_division_refuses_invalid_target_statistics(monkeypatch, tmp_path, target):
    ds = _regression_cache(monkeypatch, tmp_path)
    cache = _cache(tmp_path, ds)
    node = cache.parent / "node_1"
    node.mkdir()
    sentinel = node / "previous.txt"
    sentinel.write_text("previous partition")
    (cache / SCALING).write_text(json.dumps({"target": target}))
    with pytest.raises(FileNotFoundError, match="flexfl-preprocess"):
        ds.data_division(num_workers=2)
    assert sentinel.read_text() == "previous partition"


def test_node_folders_carry_target_statistics(monkeypatch, tmp_path):
    ds = _regression_cache(monkeypatch, tmp_path)
    cache = _cache(tmp_path, ds)
    train_y = np.load(cache / "y_train.npy")
    ds.data_division(num_workers=2)
    for worker in range(3):
        path = cache.parent / f"node_{worker}" / "target_scaling.json"
        assert path.is_file()
        target = json.loads(path.read_text())
        assert target["standardized"] is (worker != 0)
        assert target["mean"] == pytest.approx(train_y.mean())
        assert target["scale"] == pytest.approx(train_y.std())
        ds.data_path = str(path.parent)
        assert ds.target_stats() == target


def test_division_refuses_regression_cache_without_target(monkeypatch, tmp_path):
    ds = _regression_cache(monkeypatch, tmp_path)
    cache = _cache(tmp_path, ds)
    (cache / SCALING).write_text('{"scaler": "StandardScaler"}')
    node = cache.parent / "node_1"
    node.mkdir()
    sentinel = node / "previous.txt"
    sentinel.write_text("previous partition")
    with pytest.raises(FileNotFoundError, match="flexfl-preprocess"):
        ds.data_division(num_workers=2)
    assert sentinel.read_text() == "previous partition"


def test_target_stats_requires_node_file_off_cache(monkeypatch, tmp_path):
    ds = _regression_cache(monkeypatch, tmp_path)
    ds.data_path = str(_cache(tmp_path, ds).parent / "node_0")
    with pytest.raises(FileNotFoundError, match="flexfl-division"):
        ds.target_stats()


def test_constant_target_uses_unit_scale(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ds = _Regression()
    assert ds.fit_target(np.full(7, 123.0)) == {
        "fitted_on": "train",
        "n_samples": 7,
        "mean": 123.0,
        "scale": 1.0,
    }
    with pytest.raises(ValueError, match="not finite"):
        ds.fit_target(np.array([1.0, np.nan]))
