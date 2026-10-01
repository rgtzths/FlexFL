import hashlib
import random

import numpy as np
import pytest
from sklearn.preprocessing import StandardScaler

import flexfl.builtins.DatasetABC as DatasetABC_module
from flexfl.builtins.DatasetABC import DatasetABC


class _MinimalDataset(DatasetABC):

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


class _RegressionDataset(_MinimalDataset):

    @property
    def is_classification(self) -> bool:
        return False


def _build_dataset(
    monkeypatch,
    tmp_path,
    n_train,
    n_val=2,
    n_features=3,
    n_classes=2,
    dataset_cls=_MinimalDataset,
):
    metadata_dir = tmp_path / "_metadata"
    metadata_dir.mkdir()
    monkeypatch.setattr(DatasetABC_module, "DATA_FOLDER", str(tmp_path / "data"))
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    ds = dataset_cls()
    x_train = np.arange(n_train * n_features, dtype=np.float64).reshape(
        n_train, n_features
    )
    x_val = np.arange(n_val * n_features, dtype=np.float64).reshape(n_val, n_features)
    if dataset_cls is _RegressionDataset:
        y_train = np.sqrt(np.arange(n_train, dtype=np.float64))
        y_val = np.sqrt(np.arange(n_val, dtype=np.float64))
    else:
        y_train = np.array([i % n_classes for i in range(n_train)])
        y_val = np.array([i % n_classes for i in range(n_val)])
    ds.data_path = ds.default_folder
    ds.save_data(x_train, y_train, "train")
    ds.save_data(x_val, y_val, "val")
    ds.data_path = ds.default_folder
    return ds


def _division_bytes(tmp_path, ds, workers):
    return {
        f"node_{i}/{name}": (
            tmp_path / "data" / ds.name / f"node_{i}" / name
        ).read_bytes()
        for i in range(1, workers + 1)
        for name in ("x_train.npy", "y_train.npy")
    }


def _partition_digest(tmp_path, ds, workers):
    return [
        (
            len(np.load(tmp_path / "data" / ds.name / f"node_{i}" / "x_train.npy")),
            hashlib.sha256(
                np.load(
                    tmp_path / "data" / ds.name / f"node_{i}" / "x_train.npy"
                ).tobytes()
                + np.load(
                    tmp_path / "data" / ds.name / f"node_{i}" / "y_train.npy"
                ).tobytes()
            ).hexdigest()[:12],
        )
        for i in range(1, workers + 1)
    ]


def test_data_division_raises_on_empty_worker_split_iid(monkeypatch, tmp_path):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=5)
    with pytest.raises(ValueError, match="worker"):
        ds.data_division(num_workers=10, distribution="iid")


def test_data_division_raises_on_empty_worker_split_dirichlet(monkeypatch, tmp_path):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=5)
    with pytest.raises(ValueError, match="worker"):
        ds.data_division(num_workers=20, distribution="dirichlet", alpha=0.01)


def test_data_division_does_not_raise_when_workers_fit(monkeypatch, tmp_path):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=10)
    ds.data_division(num_workers=5, distribution="iid")
    for i in range(1, 6):
        node_dir = tmp_path / "data" / ds.name / f"node_{i}"
        x = np.load(node_dir / "x_train.npy")
        assert x.shape[0] > 0


@pytest.mark.parametrize("num_workers", (2, 4, 6))
def test_non_iid_division_is_byte_reproducible(monkeypatch, tmp_path, num_workers):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=400, n_classes=4)
    ds.data_division(num_workers=num_workers, distribution="non_iid")
    first = _division_bytes(tmp_path, ds, num_workers)
    for _ in range(5):
        ds.data_division(num_workers=num_workers, distribution="non_iid")
        assert _division_bytes(tmp_path, ds, num_workers) == first


@pytest.mark.parametrize("num_workers", (2, 4, 6, 12))
def test_non_iid_regression_division_is_byte_reproducible(
    monkeypatch, tmp_path, num_workers
):
    ds = _build_dataset(
        monkeypatch, tmp_path, n_train=400, dataset_cls=_RegressionDataset
    )
    assert ds.metadata["type"] == "regression"
    ds.data_division(num_workers=num_workers, distribution="non_iid")
    first = _division_bytes(tmp_path, ds, num_workers)
    for _ in range(5):
        ds.data_division(num_workers=num_workers, distribution="non_iid")
        assert _division_bytes(tmp_path, ds, num_workers) == first


@pytest.mark.parametrize("num_workers", (2, 4, 6))
def test_non_iid_ignores_the_module_level_seed(monkeypatch, tmp_path, num_workers):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=400, n_classes=4)
    random.seed(1)
    first = ds.division_non_iid(num_workers, 0.9)
    random.seed(2)
    second = ds.division_non_iid(num_workers, 0.9)
    for first_values, second_values in zip(first, second):
        for first_worker, second_worker in zip(first_values, second_values):
            assert np.array_equal(first_worker, second_worker)


@pytest.mark.parametrize("num_workers", (2, 4, 6))
def test_non_iid_never_uses_the_module_level_generator(
    monkeypatch, tmp_path, num_workers
):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=400, n_classes=4)

    def boom(*args, **kwargs):
        raise AssertionError("module-level random.sample was called")

    monkeypatch.setattr(DatasetABC_module.random, "sample", boom)
    ds.division_non_iid(num_workers, 0.9)


@pytest.mark.parametrize("num_workers", (2, 4, 6))
def test_non_iid_seed_changes_the_division(monkeypatch, tmp_path, num_workers):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=400, n_classes=4)
    divisions = {
        tuple(
            (len(x), int(y.sum()))
            for x, y in zip(*ds.division_non_iid(num_workers, 0.9, seed=seed))
        )
        for seed in range(6)
    }
    assert len(divisions) > 1


@pytest.mark.parametrize("num_workers", (2, 4, 6))
def test_non_iid_default_seed_is_42(monkeypatch, tmp_path, num_workers):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=400, n_classes=4)
    default = ds.division_non_iid(num_workers, 0.9)
    seeded = ds.division_non_iid(num_workers, 0.9, seed=42)
    for default_values, seeded_values in zip(default, seeded):
        for default_worker, seeded_worker in zip(default_values, seeded_values):
            assert np.array_equal(default_worker, seeded_worker)


def test_iid_and_dirichlet_partitions_are_unchanged(monkeypatch, tmp_path):
    ds = _build_dataset(monkeypatch, tmp_path, n_train=400, n_classes=4)
    ds.data_division(num_workers=3, distribution="iid")
    assert _partition_digest(tmp_path, ds, 3) == [
        (134, "0c15626f387f"),
        (133, "87d654e4cd4d"),
        (133, "135f4200cf07"),
    ]
    ds.data_division(num_workers=3, distribution="dirichlet")
    assert _partition_digest(tmp_path, ds, 3) == [
        (151, "1bdf0212272a"),
        (184, "8251bcc941ac"),
        (65, "7b0ac045b9fc"),
    ]
