import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from find_changed_partitions import (
    archive,
    changed_cells,
    find_cells,
    load_labels,
    main,
)

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


@pytest.mark.parametrize(
    "parameter, value",
    (("distribution_percentage", 0.8), ("alpha", 0.3), ("seed", 7)),
)
def test_find_cells_refuses_a_recipe_the_replay_cannot_reproduce(
    monkeypatch, tmp_path, parameter, value
):
    results, _ = _campaign(monkeypatch, tmp_path)
    recipe = results / "dirichlet" / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
    _write(
        recipe / "division.json",
        {"dataset": "clf_toy", "num_workers": 6, parameter: value},
    )
    with pytest.raises(ValueError, match=parameter):
        find_cells(results)


def test_find_cells_accepts_the_recipe_values_the_sweep_records(monkeypatch, tmp_path):
    results, _ = _campaign(monkeypatch, tmp_path)
    recipe = results / "dirichlet" / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
    _write(
        recipe / "division.json",
        {
            "dataset": "clf_toy",
            "num_workers": 6,
            "distribution_percentage": 0.9,
            "alpha": 0.5,
            "seed": 42,
        },
    )
    assert len(find_cells(results)) == 2


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


def test_archive_refuses_a_destination_inside_the_results_tree(monkeypatch, tmp_path):
    results, data = _campaign(monkeypatch, tmp_path)
    changed = changed_cells(find_cells(results), _ReversedDirichlet, DatasetABC, data)
    with pytest.raises(ValueError, match="inside"):
        archive(changed, results, results / "archive")
    assert changed[0].exists()
    assert not (results / "archive").exists()


def test_archive_moves_nothing_when_any_target_exists(monkeypatch, tmp_path):
    results, data = _campaign(monkeypatch, tmp_path)
    changed = changed_cells(find_cells(results), _ReversedNonIid, DatasetABC, data)
    changed += changed_cells(find_cells(results), _ReversedDirichlet, DatasetABC, data)
    archive_root = tmp_path / "archive"
    (archive_root / changed[1].relative_to(results)).mkdir(parents=True)
    with pytest.raises(FileExistsError):
        archive(changed, results, archive_root)
    assert all(cell.exists() for cell in changed)


def test_apply_requires_an_archive_destination():
    with pytest.raises(SystemExit):
        main(["--old-ref", "HEAD", "--apply"])


class _ReversedWhen(DatasetABC):

    def reversed_here(self, num_workers):
        return False

    def division_non_iid_dirichlet(self, num_workers, alpha=0.5, seed=42):
        x, y = super().division_non_iid_dirichlet(num_workers, alpha, seed)
        if self.reversed_here(num_workers):
            return x[::-1], y[::-1]
        return x, y


class _ReversedAtSixWorkers(_ReversedWhen):

    def reversed_here(self, num_workers):
        return num_workers == 6


class _ReversedForToy(_ReversedWhen):

    def reversed_here(self, num_workers):
        return self.name == "clf_toy"


class _ReversedForRegression(_ReversedWhen):

    def reversed_here(self, num_workers):
        return self.metadata["type"] == "regression"


def _dirichlet_cells(tmp_path, cells, datasets, y_regression=None):
    metadata_dir = tmp_path / "_metadata"
    for name, task_type in datasets.items():
        _write(metadata_dir / f"{name}.json", {"type": task_type})
        cache = tmp_path / "data" / name / "_data"
        cache.mkdir(parents=True)
        if task_type == "classification":
            y = np.array([i % 2 for i in range(600)])
        elif y_regression is not None:
            y = y_regression
        else:
            y = np.random.default_rng(1).normal(size=600)
        np.save(cache / "y_train.npy", y)
    results = tmp_path / "results"
    for combo, name, num_workers in cells:
        _write(
            results / "dirichlet" / combo / name / "division.json",
            {"dataset": name, "num_workers": num_workers},
        )
    return results, tmp_path / "data", metadata_dir


def test_verdicts_are_not_shared_across_worker_totals(monkeypatch, tmp_path):
    results, data, metadata_dir = _dirichlet_cells(
        tmp_path,
        [("a", "clf_toy", 6), ("b", "clf_toy", 8)],
        {"clf_toy": "classification"},
    )
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    changed = changed_cells(
        find_cells(results), _ReversedAtSixWorkers, DatasetABC, data
    )
    assert changed == [results / "dirichlet" / "a" / "clf_toy"]


def test_verdicts_are_not_shared_across_datasets(monkeypatch, tmp_path):
    results, data, metadata_dir = _dirichlet_cells(
        tmp_path,
        [("a", "clf_other", 6), ("a", "clf_toy", 6)],
        {"clf_toy": "classification", "clf_other": "classification"},
    )
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    changed = changed_cells(find_cells(results), _ReversedForToy, DatasetABC, data)
    assert changed == [results / "dirichlet" / "a" / "clf_toy"]


def test_regression_cells_are_replayed_as_regression(monkeypatch, tmp_path):
    results, data, metadata_dir = _dirichlet_cells(
        tmp_path,
        [("a", "clf_toy", 6), ("a", "reg_toy", 6)],
        {"clf_toy": "classification", "reg_toy": "regression"},
    )
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    changed = changed_cells(
        find_cells(results), _ReversedForRegression, DatasetABC, data
    )
    assert changed == [results / "dirichlet" / "a" / "reg_toy"]


def test_load_labels_keeps_the_cached_target_dtype(monkeypatch, tmp_path):
    y = np.random.default_rng(1).normal(size=600).astype(np.float32)
    _, data, metadata_dir = _dirichlet_cells(
        tmp_path, [], {"reg_toy": "regression"}, y_regression=y
    )
    monkeypatch.setattr(DatasetABC_module, "METADATA_FOLDER", str(metadata_dir))
    labels, task_type = load_labels(data, "reg_toy")
    assert task_type == "regression"
    assert labels.dtype == np.float32
    assert np.array_equal(labels, y)


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def two_commit_repo(monkeypatch, tmp_path):
    current = Path(DatasetABC_module.__file__).read_text()
    old = current.replace(
        "        return self.enforce_min_samples(workers_x, workers_y)\n\n"
        "    def division_worker",
        "        return workers_x[::-1], workers_y[::-1]\n\n    def division_worker",
    )
    assert old != current
    repo = tmp_path / "repo"
    module = repo / "src" / "flexfl" / "builtins" / "DatasetABC.py"
    module.parent.mkdir(parents=True)
    _git(tmp_path, "init", "-q", str(repo))
    module.write_text(old)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "old")
    module.write_text(current)
    _git(repo, "commit", "-qam", "new")
    results, data = _campaign(monkeypatch, tmp_path)
    args = [
        "--repo-root",
        str(repo),
        "--results",
        str(results),
        "--data-dir",
        str(data),
    ]
    cell = results / "dirichlet" / "atnog-test1_2_hobbit_2_samwise_2" / "clf_toy"
    return args, cell, tmp_path / "archive"


def test_main_lists_changed_cells_without_moving_them(two_commit_repo, capsys):
    args, cell, archive_root = two_commit_repo
    main(["--old-ref", "HEAD~1", *args, "--archive-to", str(archive_root)])
    output = capsys.readouterr()
    assert output.out == f"{cell}\t1\n"
    assert "1 of 2 cells changed, 1 _SUCCESS runs" in output.err
    assert cell.exists()
    assert not archive_root.exists()


def test_main_apply_moves_the_changed_cells(two_commit_repo, capsys):
    args, cell, archive_root = two_commit_repo
    main(["--old-ref", "HEAD~1", *args, "--archive-to", str(archive_root), "--apply"])
    assert not cell.exists()
    moved = archive_root / cell.relative_to(cell.parents[2])
    assert (moved / "CentralizedSync" / "rep_1" / "_SUCCESS").exists()
    assert "archived 1 cells" in capsys.readouterr().err


def test_main_against_the_installed_code_lists_nothing(two_commit_repo, capsys):
    args, _, _ = two_commit_repo
    main(["--old-ref", "HEAD", *args])
    output = capsys.readouterr()
    assert output.out == ""
    assert "0 of 2 cells changed, 0 _SUCCESS runs" in output.err
