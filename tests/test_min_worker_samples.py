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
        (2060, 20, 5),
        (2000, 21, 4),
        (1000, 10, 5),
        (1000, 11, 4),
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


def test_enforce_min_samples_tops_up_from_the_largest_not_the_first_eligible_worker():
    xs = [np.arange(0, 0), np.arange(0, 30), np.arange(30, 530), np.arange(530, 1000)]
    ys = [x.astype(np.float64) for x in xs]
    out_x, _ = DatasetABC.enforce_min_samples(xs, ys)
    assert [len(p) for p in out_x] == [10, 30, 490, 470]
    assert np.array_equal(out_x[0], np.arange(520, 530))


def test_enforce_min_samples_uses_the_floor_for_its_worker_count():
    xs = [np.arange(0, 0)]
    xs += [np.arange(i * 111, (i + 1) * 111) for i in range(8)]
    xs += [np.arange(888, 1000)]
    ys = [x.astype(np.float64) for x in xs]
    out_x, _ = DatasetABC.enforce_min_samples(xs, ys)
    assert len(out_x[0]) == 5


def test_enforce_min_samples_tops_up_needy_workers_in_index_order():
    xs = [np.arange(0, 1), np.arange(1, 2), np.arange(2, 1000)]
    ys = [x.astype(np.float64) for x in xs]
    out_x, _ = DatasetABC.enforce_min_samples(xs, ys)
    assert np.array_equal(out_x[0], np.concatenate([[0], np.arange(991, 1000)]))
    assert np.array_equal(out_x[1], np.concatenate([[1], np.arange(982, 991)]))
    assert np.array_equal(out_x[2], np.arange(2, 982))


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


@pytest.mark.parametrize(
    "dataset_cls, y, num_workers",
    (
        (_ClassificationDataset, np.zeros(500, dtype=np.int64), 4),
        (_RegressionDataset, np.full(500, 3.0), 4),
        (_ClassificationDataset, np.array([i % 3 for i in range(500)]), 1),
    ),
)
def test_non_iid_without_out_of_class_workers_keeps_every_sample(
    monkeypatch, tmp_path, dataset_cls, y, num_workers
):
    ds = _dataset(monkeypatch, tmp_path, y, dataset_cls)
    parts, _ = ds.division_non_iid(num_workers, 0.9)
    assert len(parts) == num_workers
    assert min(len(p) for p in parts) >= _expected_floor(len(y), num_workers)
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


def _division_entry(monkeypatch, tmp_path, y):
    ds = _dataset(monkeypatch, tmp_path, y, _ClassificationDataset)
    monkeypatch.setattr(ds, "check_scaled_cache", lambda: None)
    monkeypatch.setattr(ds, "target_stats", lambda: None)
    monkeypatch.setattr(ds, "division_master", lambda target=None: None)
    written = []
    monkeypatch.setattr(
        ds, "division_worker", lambda x, *args, **kwargs: written.append(len(x))
    )
    return ds, written


def _division_with_sizes(monkeypatch, tmp_path, sizes):
    ds, written = _division_entry(monkeypatch, tmp_path, _binary_labels(sum(sizes)))
    monkeypatch.setattr(
        ds,
        "division_iid",
        lambda num_workers: (
            [np.zeros((size, 1)) for size in sizes],
            [np.zeros(size) for size in sizes],
        ),
    )
    return ds, written


def test_data_division_rejects_a_worker_below_the_floor(monkeypatch, tmp_path):
    ds, _ = _division_with_sizes(monkeypatch, tmp_path, [3, 397])
    with pytest.raises(ValueError, match="worker 1/2 received 3 training samples"):
        ds.data_division(num_workers=2, distribution="iid")


def test_data_division_accepts_a_worker_exactly_at_the_floor(monkeypatch, tmp_path):
    ds, written = _division_with_sizes(monkeypatch, tmp_path, [10, 390])
    ds.data_division(num_workers=2, distribution="iid")
    assert written == [10, 390]


@pytest.mark.parametrize("sizes", ([9, 391], [7, 393]))
def test_data_division_rejects_a_worker_just_below_the_floor(
    monkeypatch, tmp_path, sizes
):
    ds, written = _division_with_sizes(monkeypatch, tmp_path, sizes)
    with pytest.raises(ValueError, match=f"received {sizes[0]} training samples"):
        ds.data_division(num_workers=2, distribution="iid")
    assert written == []


def test_data_division_accepts_a_dirichlet_split_it_had_to_top_up(
    monkeypatch, tmp_path
):
    ds, written = _division_entry(monkeypatch, tmp_path, _binary_labels(2060))
    ds.data_division(num_workers=44, distribution="dirichlet")
    assert len(written) == 44
    assert sum(written) == 2060
    assert min(written) == _expected_floor(2060, 44)
