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


def _build_dataset(monkeypatch, tmp_path, n_train, n_val=2, n_features=3):
    metadata_dir = tmp_path / "_metadata"
    metadata_dir.mkdir()
    monkeypatch.setattr(DatasetABC_module, "DATA_FOLDER", str(tmp_path / "data"))
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    ds = _MinimalDataset()
    x_train = np.arange(n_train * n_features, dtype=np.float64).reshape(n_train, n_features)
    y_train = np.array([i % 2 for i in range(n_train)])
    x_val = np.arange(n_val * n_features, dtype=np.float64).reshape(n_val, n_features)
    y_val = np.array([i % 2 for i in range(n_val)])
    ds.data_path = ds.default_folder
    ds.save_data(x_train, y_train, "train")
    ds.save_data(x_val, y_val, "val")
    ds.data_path = ds.default_folder
    return ds


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
