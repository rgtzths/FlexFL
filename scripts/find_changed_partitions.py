#!/usr/bin/env python3
"""List, and optionally archive, sweep cells whose worker partitions differ
between an older DatasetABC (read from a git ref) and the installed one.

A cell is results/<strategy>/<combo>/<dataset>/ holding a division.json
without "split_version" 2 or later, which cells divided by the old code lack. For
each distinct (dataset, strategy, num_workers) the old and new division
functions are run on data/<dataset>/_data/y_train.npy with row indices in place
of features, so only partition membership and order are compared and no
node_* folder is written. Changed cells are printed with their _SUCCESS count;
with --apply each is moved under --archive-to, keeping its relative path, so the
resumable sweep reruns it. --archive-to must lie outside --results, and nothing
moves when any archive target already exists.
"""

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from flexfl.builtins import DatasetABC as current_module

STRATEGIES = ("non_iid", "dirichlet")
MODULE_PATH = "src/flexfl/builtins/DatasetABC.py"


def load_module_at_ref(ref, repo_root):
    source = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{ref}:{MODULE_PATH}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(source)
    spec = importlib.util.spec_from_file_location(f"DatasetABC_{ref}", handle.name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    Path(handle.name).unlink()
    return module


def make_probe(division_cls, name, y, task_type):
    def __init__(self):
        self.name = name
        self.default_folder = self.data_path = "unused"
        self.metadata = {"type": task_type}

    def load_data(self, split, loader=None):
        return np.arange(len(y)).reshape(-1, 1), y

    probe_cls = type(
        "PartitionProbe",
        (division_cls,),
        {"__init__": __init__, "load_data": load_data},
    )
    probe_cls.__abstractmethods__ = frozenset()
    return probe_cls()


def partition_digests(division_cls, name, strategy, num_workers, y, task_type):
    probe = make_probe(division_cls, name, y, task_type)
    if strategy == "dirichlet":
        parts, _ = probe.division_non_iid_dirichlet(num_workers, 0.5)
    else:
        parts, _ = probe.division_non_iid(num_workers, 0.9)
    return [
        hashlib.sha256(np.ascontiguousarray(part).tobytes()).hexdigest()
        for part in parts
    ]


def find_cells(results_root):
    cells = []
    for strategy in STRATEGIES:
        for division_json in sorted(
            Path(results_root, strategy).glob("*/*/division.json")
        ):
            recipe = json.loads(division_json.read_text())
            if recipe.get("split_version", 1) >= 2:
                continue
            cells.append(
                (
                    division_json.parent,
                    strategy,
                    recipe["dataset"],
                    recipe["num_workers"],
                )
            )
    return cells


def load_labels(data_dir, name):
    y = np.load(Path(data_dir, name, "_data", "y_train.npy"), allow_pickle=True)
    metadata = json.loads(
        Path(current_module.METADATA_FOLDER, f"{name}.json").read_text()
    )
    return y, metadata["type"]


def changed_cells(cells, old_cls, new_cls, data_dir):
    verdicts, labels, changed = {}, {}, []
    for cell, strategy, name, num_workers in cells:
        key = (name, strategy, num_workers)
        if key not in verdicts:
            if name not in labels:
                labels[name] = load_labels(data_dir, name)
            y, task_type = labels[name]
            verdicts[key] = partition_digests(
                old_cls, name, strategy, num_workers, y, task_type
            ) != partition_digests(new_cls, name, strategy, num_workers, y, task_type)
        if verdicts[key]:
            changed.append(cell)
    return changed


def archive(cells, results_root, archive_root):
    results_root = Path(results_root).resolve()
    archive_root = Path(archive_root).resolve()
    if archive_root == results_root or results_root in archive_root.parents:
        raise ValueError(
            f"{archive_root} is inside {results_root}, where the assembler would "
            "still read the archived runs; choose a directory outside it"
        )
    targets = [
        archive_root / Path(cell).resolve().relative_to(results_root) for cell in cells
    ]
    for target in targets:
        if target.exists():
            raise FileExistsError(f"{target} already exists; refusing to overwrite")
    for cell, target in zip(cells, targets):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(cell), str(target))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--old-ref", required=True)
    parser.add_argument("--results", default="results")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--archive-to")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and not args.archive_to:
        parser.error("--apply needs --archive-to")

    old_cls = load_module_at_ref(args.old_ref, args.repo_root).DatasetABC
    cells = find_cells(args.results)
    changed = changed_cells(cells, old_cls, current_module.DatasetABC, args.data_dir)
    runs = 0
    for cell in changed:
        successes = len(list(cell.glob("*/rep_*/_SUCCESS")))
        runs += successes
        print(f"{cell}\t{successes}")
    print(
        f"{len(changed)} of {len(cells)} cells changed, {runs} _SUCCESS runs",
        file=sys.stderr,
    )
    if args.apply:
        archive(changed, args.results, args.archive_to)
        print(f"archived {len(changed)} cells to {args.archive_to}", file=sys.stderr)


if __name__ == "__main__":
    main()
