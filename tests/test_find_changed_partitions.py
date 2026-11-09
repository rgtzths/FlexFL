import json

import numpy as np
import pytest
from find_changed_partitions import archive, changed_cells, find_cells, main

import flexfl.builtins.DatasetABC as DatasetABC_module
from flexfl.builtins.DatasetABC import DatasetABC


class _ReversedDirichlet(DatasetABC):

    def division_non_iid_dirichlet(self, num_workers, alpha=0.5, seed=42):
        x, y = super().division_non_iid_dirichlet(num_workers, alpha, seed)
        return x[::-1], y[::-1]


class _ReversedNonIid(DatasetABC):

    def division_non_iid(self, num_workers, distribution_percentage, seed=42):
        x, y = super().division_non_iid(num_workers, distribution_percentage, seed)
        return x[::-1], y[::-1]


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _campaign(monkeypatch, tmp_path):
    metadata_dir = tmp_path / "_metadata"
    _write(metadata_dir / "clf_toy.json", {"type": "classification"})
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    cache = tmp_path / "data" / "clf_toy" / "_data"
    cache.mkdir(parents=True)
    np.save(cache / "y_train.npy", np.array([i % 2 for i in range(600)]))
    results = tmp_path / "results"
    for strategy in ("non_iid", "dirichlet"):
        cell = results / strategy / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
        _write(
            cell / "division.json",
            {"dataset": "clf_toy", "num_workers": 6, "strategy": strategy},
        )
        sentinel = cell / "CentralizedSync" / "rep_1" / "_SUCCESS"
        sentinel.parent.mkdir(parents=True)
        sentinel.touch()
    iid_cell = results / "iid" / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
    _write(iid_cell / "division.json", {"dataset": "clf_toy", "num_workers": 6})
    return results, tmp_path / "data"


def test_find_cells_lists_only_non_iid_and_dirichlet_cells(monkeypatch, tmp_path):
    results, _ = _campaign(monkeypatch, tmp_path)
    cells = find_cells(results)
    assert [(strategy, name, n) for _, strategy, name, n in cells] == [
        ("non_iid", "clf_toy", 6),
        ("dirichlet", "clf_toy", 6),
    ]


@pytest.mark.parametrize("split_version", (2, 3))
def test_find_cells_skips_cells_already_divided_by_split_version_2_or_later(
    monkeypatch, tmp_path, split_version
):
    results, _ = _campaign(monkeypatch, tmp_path)
    recipe = results / "dirichlet" / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
    _write(
        recipe / "division.json",
        {"dataset": "clf_toy", "num_workers": 6, "split_version": split_version},
    )
    assert [strategy for _, strategy, _, _ in find_cells(results)] == ["non_iid"]


def test_identical_division_code_changes_no_cell(monkeypatch, tmp_path):
    results, data = _campaign(monkeypatch, tmp_path)
    assert changed_cells(find_cells(results), DatasetABC, DatasetABC, data) == []


def test_changed_division_flags_only_the_cells_it_changes(monkeypatch, tmp_path):
    results, data = _campaign(monkeypatch, tmp_path)
    changed = changed_cells(find_cells(results), _ReversedDirichlet, DatasetABC, data)
    assert changed == [
        results / "dirichlet" / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
    ]


def test_changed_non_iid_division_flags_only_the_non_iid_cell(monkeypatch, tmp_path):
    results, data = _campaign(monkeypatch, tmp_path)
    changed = changed_cells(find_cells(results), _ReversedNonIid, DatasetABC, data)
    assert changed == [
        results / "non_iid" / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
    ]


def test_archive_moves_cells_and_refuses_to_overwrite(monkeypatch, tmp_path):
    results, data = _campaign(monkeypatch, tmp_path)
    changed = changed_cells(find_cells(results), _ReversedDirichlet, DatasetABC, data)
    archive_root = tmp_path / "archive"
    archive(changed, results, archive_root)
    moved = archive_root / "dirichlet" / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
    assert (moved / "CentralizedSync" / "rep_1" / "_SUCCESS").exists()
    assert not changed[0].exists()
    changed[0].mkdir(parents=True)
    with pytest.raises(FileExistsError):
        archive(changed, results, archive_root)


def test_apply_requires_an_archive_destination():
    with pytest.raises(SystemExit):
        main(["--old-ref", "HEAD", "--apply"])
