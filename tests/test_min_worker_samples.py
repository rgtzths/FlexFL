import numpy as np
import pytest
from sklearn.preprocessing import StandardScaler

import flexfl.builtins.DatasetABC as DatasetABC_module
from flexfl.builtins.DatasetABC import DatasetABC


class _ClassificationDataset(DatasetABC):

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


class _RegressionDataset(_ClassificationDataset):

    @property
    def is_classification(self) -> bool:
        return False


def _dataset(monkeypatch, tmp_path, y, dataset_cls):
    metadata_dir = tmp_path / "_metadata"
    metadata_dir.mkdir()
    monkeypatch.setattr(DatasetABC_module, "DATA_FOLDER", str(tmp_path / "data"))
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    ds = dataset_cls()
    ds.metadata["type"] = (
        "classification" if dataset_cls is _ClassificationDataset else "regression"
    )
    x = np.arange(len(y), dtype=np.float64).reshape(-1, 1)
    monkeypatch.setattr(ds, "load_data", lambda split, loader=None: (x, y))
    return ds


def _expected_floor(n_samples, num_workers):
    return max(1, min(10, int(0.05 * n_samples / num_workers)))


def _long_tail_regression_targets():
    rng = np.random.default_rng(0)
    bulk = rng.normal(10.0, 2.0, size=2500)
    tail = np.array([25.0, 27.5, 30.0, 33.0, 36.0, 40.0])
    return np.concatenate([bulk, tail])


def _binary_labels(n_samples):
    return np.array([i % 2 for i in range(n_samples)])


@pytest.mark.parametrize(
    "n_samples, num_workers, expected",
    (
        (2060, 56, 1),
        (2506, 6, 10),
        (23084, 40, 10),
        (4564, 40, 5),
        (100, 10, 1),
        (5, 10, 1),
    ),
)
def test_min_worker_samples_is_five_percent_of_a_share_capped_at_ten(
    n_samples, num_workers, expected
):
    assert DatasetABC.min_worker_samples(n_samples, num_workers) == expected


def test_enforce_min_samples_returns_valid_partitions_untouched():
    xs = [np.arange(0, 40), np.arange(40, 100)]
    ys = [np.zeros(40), np.ones(60)]
    out_x, out_y = DatasetABC.enforce_min_samples(xs, ys)
    assert out_x is xs and out_y is ys


def test_enforce_min_samples_tops_up_from_the_largest_worker():
    xs = [np.arange(0, 2), np.arange(2, 700), np.arange(700, 800)]
    ys = [x.astype(np.float64) for x in xs]
    out_x, out_y = DatasetABC.enforce_min_samples(xs, ys)
    assert [len(p) for p in out_x] == [10, 690, 100]
    assert np.array_equal(
        out_x[0], np.concatenate([np.arange(0, 2), np.arange(692, 700)])
    )
    assert np.array_equal(out_x[1], np.arange(2, 692))
    assert all(np.array_equal(px, py) for px, py in zip(out_x, out_y))


def test_enforce_min_samples_takes_from_the_lowest_index_largest_worker_on_ties():
    xs = [np.arange(0, 1), np.arange(1, 401), np.arange(401, 801)]
    ys = [x.astype(np.float64) for x in xs]
    out_x, _ = DatasetABC.enforce_min_samples(xs, ys)
    assert [len(p) for p in out_x] == [10, 391, 400]
    assert np.array_equal(out_x[1], np.arange(1, 392))
    assert np.array_equal(out_x[2], np.arange(401, 801))


def test_enforce_min_samples_leaves_infeasible_partitions_for_the_guard():
    xs = [np.arange(0, 1), np.array([], dtype=np.int64), np.array([], dtype=np.int64)]
    ys = [x.astype(np.float64) for x in xs]
    out_x, _ = DatasetABC.enforce_min_samples(xs, ys)
    assert [len(p) for p in out_x] == [1, 0, 0]


@pytest.mark.parametrize("num_workers", (40, 44, 48, 56))
def test_non_iid_regression_long_tail_meets_the_floor_and_keeps_every_sample(
    monkeypatch, tmp_path, num_workers
):
    y = _long_tail_regression_targets()
    ds = _dataset(monkeypatch, tmp_path, y, _RegressionDataset)
    parts, _ = ds.division_non_iid(num_workers, 0.9)
    floor = _expected_floor(len(y), num_workers)
    assert min(len(p) for p in parts) >= floor
    assigned = np.sort(np.concatenate([p.ravel() for p in parts]))
    assert np.array_equal(assigned, np.arange(len(y), dtype=np.float64))


@pytest.mark.parametrize("num_workers", (6, 13, 36, 56))
def test_non_iid_classification_keeps_every_sample(monkeypatch, tmp_path, num_workers):
    y = np.array([i % 3 for i in range(4567)])
    ds = _dataset(monkeypatch, tmp_path, y, _ClassificationDataset)
    parts, _ = ds.division_non_iid(num_workers, 0.9)
    assigned = np.sort(np.concatenate([p.ravel() for p in parts]))
    assert np.array_equal(assigned, np.arange(len(y), dtype=np.float64))


@pytest.mark.parametrize("num_workers", (36, 40, 44, 52, 56))
def test_dirichlet_binary_meets_the_floor_and_keeps_every_sample(
    monkeypatch, tmp_path, num_workers
):
    y = _binary_labels(2060)
    ds = _dataset(monkeypatch, tmp_path, y, _ClassificationDataset)
    parts, labels = ds.division_non_iid_dirichlet(num_workers, 0.5)
    floor = _expected_floor(len(y), num_workers)
    assert min(len(p) for p in parts) >= floor
    assigned = np.sort(np.concatenate([p.ravel() for p in parts]))
    assert np.array_equal(assigned, np.arange(len(y), dtype=np.float64))
    for part, label in zip(parts, labels):
        assert np.array_equal(y[part.ravel().astype(int)], label)


@pytest.mark.parametrize("num_workers", (36, 44, 56))
def test_dirichlet_three_classes_meets_the_floor_and_keeps_every_sample(
    monkeypatch, tmp_path, num_workers
):
    y = np.array([i % 3 for i in range(3000)])
    ds = _dataset(monkeypatch, tmp_path, y, _ClassificationDataset)
    parts, labels = ds.division_non_iid_dirichlet(num_workers, 0.5)
    floor = _expected_floor(len(y), num_workers)
    assert min(len(p) for p in parts) >= floor
    assigned = np.sort(np.concatenate([p.ravel() for p in parts]))
    assert np.array_equal(assigned, np.arange(len(y), dtype=np.float64))
    for part, label in zip(parts, labels):
        assert np.array_equal(y[part.ravel().astype(int)], label)


def test_data_division_rejects_a_worker_below_the_floor(monkeypatch, tmp_path):
    y = _binary_labels(400)
    ds = _dataset(monkeypatch, tmp_path, y, _ClassificationDataset)
    monkeypatch.setattr(ds, "check_scaled_cache", lambda: None)
    monkeypatch.setattr(ds, "target_stats", lambda: None)
    monkeypatch.setattr(ds, "division_master", lambda target=None: None)
    monkeypatch.setattr(
        ds,
        "division_iid",
        lambda num_workers: (
            [np.zeros((3, 1)), np.zeros((397, 1))],
            [np.zeros(3), np.zeros(397)],
        ),
    )
    with pytest.raises(ValueError, match="worker 1/2 received 3 training samples"):
        ds.data_division(num_workers=2, distribution="iid")
