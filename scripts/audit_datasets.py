#!/usr/bin/env python3
"""Audit raw Benchmark datasets at the pinned revision.

Reads dataset names and tier membership, splits rows as production does, and
writes JSON and CSV with provenance. Run from the repository root:

    .venv/bin/python scripts/audit_datasets.py --names names.txt \
        --tier20 tier20.txt --out-json audit.json --out-csv audit.csv
"""

import argparse
import csv
import json
import subprocess
from importlib.metadata import version
from pathlib import Path

import numpy as np
from audit_common import read_lines, sha256_file
from scipy import stats

from flexfl.builtins.DatasetABC import DatasetABC
from flexfl.datasets.Benchmark import (
    HF_DATASET,
    HF_REVISION,
    SENTINEL,
    is_clf,
    load_raw,
)

VAL_SIZE = 0.2
TEST_SIZE = 0.2
SPLIT_KEYS = ("x_train", "y_train", "x_val", "y_val", "x_test", "y_test")
SENTINEL_CANDIDATES = {-99999.0, -9999.0, SENTINEL, -99.0, 999.0, 9999.0, 99999.0}


def load_splits(name, revision, *, keep_sentinel_rows):
    x, y = load_raw(name, revision, keep_sentinel_rows)
    arrays = DatasetABC.split_data(x, y, VAL_SIZE, TEST_SIZE)
    return dict(zip(SPLIT_KEYS, arrays))


def _top_value(col):
    vals, counts = np.unique(col, return_counts=True)
    i = int(np.argmax(counts))
    return float(vals[i]), counts[i] / col.size, vals.size


def audit(name, data, tier20):
    xtr, xva, xte = data["x_train"], data["x_val"], data["x_test"]
    ytr = data["y_train"]
    yall = np.concatenate([data["y_train"], data["y_val"], data["y_test"]])
    xall = np.concatenate([xtr, xva, xte])
    clf = is_clf(name)
    row = {"dataset": name, "tier20": name in tier20, "task": "clf" if clf else "reg"}
    row["n_train"], row["n_val"], row["n_test"] = len(xtr), len(xva), len(xte)
    row["n_feat"] = xtr.shape[1]
    row["n_nonfinite"] = int(
        (~np.isfinite(xall)).sum() + (~np.isfinite(yall.astype(np.float64))).sum()
    )
    row["n_sentinel_cells"] = int((xall == SENTINEL).sum())
    row["n_all_sentinel_rows"] = int(np.all(xall == SENTINEL, axis=1).sum())

    mean = xtr.mean(axis=0)
    std = xtr.std(axis=0)
    const = std == 0
    row["n_const"] = int(const.sum())
    scale = np.where(const, 1.0, std)

    lo, hi = xtr.min(axis=0), xtr.max(axis=0)
    nuniq_by_col = []
    near_const, binary, sentinel_hits = 0, 0, []
    for j in range(xtr.shape[1]):
        v, frac, nuniq = _top_value(xtr[:, j])
        nuniq_by_col.append(nuniq)
        if nuniq <= 2:
            binary += 1
        if not const[j] and frac >= 0.99:
            near_const += 1
        if nuniq > 2 and frac >= 0.01:
            z = abs(v - mean[j]) / scale[j]
            is_edge = v in (lo[j], hi[j])
            if v in SENTINEL_CANDIDATES or (is_edge and z > 4):
                sentinel_hits.append(f"f{j}={v:g}({frac:.1%},z={z:.1f})")
    row["n_near_const"] = near_const
    row["n_binary"] = binary
    row["n_sentinel_cand"] = len(sentinel_hits)
    row["sentinel_examples"] = ";".join(sentinel_hits[:4])

    z_all = np.abs((xall - mean) / scale)
    z_feat = z_all.max(axis=0)
    row["max_abs_z"] = float(z_feat.max())
    row["worst_feat"] = int(z_feat.argmax())
    row["n_feat_z_gt10"] = int((z_feat > 10).sum())
    row["n_feat_z_gt50"] = int((z_feat > 50).sum())
    row["frac_cells_z_gt10"] = float((z_all > 10).mean())

    cont = [j for j in range(xtr.shape[1]) if not const[j] and nuniq_by_col[j] > 10]
    if cont:
        kurt = stats.kurtosis(xtr[:, cont], axis=0, fisher=True, bias=False)
        skew = stats.skew(xtr[:, cont], axis=0, bias=False)
        row["n_continuous"] = len(cont)
        row["max_excess_kurtosis"] = float(np.nanmax(kurt))
        row["n_kurt_gt20"] = int((kurt > 20).sum())
        row["n_abs_skew_gt5"] = int((np.abs(skew) > 5).sum())
    else:
        row["n_continuous"] = 0
        row["max_excess_kurtosis"] = 0.0
        row["n_kurt_gt20"] = 0
        row["n_abs_skew_gt5"] = 0

    xvt = np.concatenate([xva, xte])
    out_range = ((xvt < lo) | (xvt > hi)).mean(axis=0)
    row["max_frac_outside_train_range"] = float(out_range.max())

    _, inv, counts = np.unique(xtr, axis=0, return_inverse=True, return_counts=True)
    row["frac_dup_rows_train"] = float(1 - len(counts) / len(xtr))
    if clf and len(counts) < len(xtr):
        inv = inv.ravel()
        conflict = 0
        for g in np.where(counts > 1)[0]:
            if len(np.unique(ytr[inv == g])) > 1:
                conflict += counts[g]
        row["frac_dup_label_conflict"] = float(conflict / len(xtr))
    else:
        row["frac_dup_label_conflict"] = 0.0
    _, col_counts = np.unique(xtr.T, axis=0, return_counts=True)
    row["n_dup_cols"] = int(xtr.shape[1] - len(col_counts))

    yf = ytr.astype(np.float64)
    corrs = []
    multiclass = clf and len(np.unique(ytr)) > 2
    if not multiclass:
        for j in range(xtr.shape[1]):
            if const[j]:
                continue
            c = np.corrcoef(xtr[:, j], yf)[0, 1]
            if np.isfinite(c):
                corrs.append(abs(c))
    row["max_abs_corr_feat_y"] = float(max(corrs)) if corrs else float("nan")

    if clf:
        _, cc = np.unique(yall, return_counts=True)
        row["n_classes"] = int(cc.size)
        row["min_class_frac"] = float(cc.min() / cc.sum())
        row["imbalance_ratio"] = float(cc.max() / cc.min())
    else:
        y = yall.astype(np.float64)
        row["y_mean"], row["y_std"] = float(y.mean()), float(y.std())
        row["y_min"], row["y_max"] = float(y.min()), float(y.max())
        row["y_median"] = float(np.median(y))
        row["y_skew"] = float(stats.skew(y, bias=False))
        row["y_excess_kurtosis"] = float(stats.kurtosis(y, bias=False))
        row["y_max_z"] = float(np.abs((y - y.mean()) / (y.std() or 1)).max())
        row["y_top_value_frac"] = _top_value(y)[1]
        if y.min() >= 0:
            row["y_log1p_skew"] = float(stats.skew(np.log1p(y), bias=False))
        else:
            row["y_log1p_skew"] = float("nan")
    return row


def flags(row):
    found = []
    if row["n_nonfinite"]:
        found.append("nonfinite")
    if row["n_const"]:
        found.append("constant_features")
    if row["n_feat_z_gt50"]:
        found.append("extreme_outliers_z50")
    elif row["n_feat_z_gt10"]:
        found.append("outliers_z10")
    if row["n_kurt_gt20"]:
        found.append("heavy_tails")
    if row["n_sentinel_cand"]:
        found.append("sentinel_candidates")
    if row["n_all_sentinel_rows"]:
        found.append("all_sentinel_rows")
    if row["frac_dup_rows_train"] > 0.05:
        found.append("many_duplicate_rows")
    if row["frac_dup_label_conflict"] > 0.01:
        found.append("duplicate_label_conflicts")
    if row["n_dup_cols"]:
        found.append("duplicate_columns")
    if np.isfinite(row["max_abs_corr_feat_y"]) and row["max_abs_corr_feat_y"] > 0.98:
        found.append("leak_candidate")
    if row["max_frac_outside_train_range"] > 0.01:
        found.append("split_shift")
    if row["task"] == "clf" and row["imbalance_ratio"] > 10:
        found.append("class_imbalance")
    if row["task"] == "reg":
        if abs(row["y_skew"]) > 2:
            found.append("skewed_target")
        if row["y_max_z"] > 10:
            found.append("target_outliers")
    return found


def provenance():
    root = Path(__file__).resolve().parent.parent
    sources = (
        "scripts/audit_common.py",
        "scripts/audit_datasets.py",
        "scripts/audit_central_sanity.py",
        "scripts/render_dataset_audit.py",
        "src/flexfl/datasets/Benchmark.py",
        "src/flexfl/builtins/DatasetABC.py",
    )
    return {
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            ).strip()
        ),
        "sources_sha256": {path: sha256_file(root / path) for path in sources},
        "hf_dataset": HF_DATASET,
        "hf_revision": HF_REVISION,
        "val_size": VAL_SIZE,
        "test_size": TEST_SIZE,
        "versions": {
            package: version(package)
            for package in ("numpy", "scipy", "scikit-learn", "datasets")
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", type=Path, required=True)
    parser.add_argument("--tier20", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    args = parser.parse_args(argv)
    names = read_lines(args.names)
    tier20 = set(read_lines(args.tier20))
    prov = provenance()
    rows = []
    for name in names:
        data = load_splits(name, prov["hf_revision"], keep_sentinel_rows=True)
        row = audit(name, data, tier20)
        row["flags"] = ",".join(flags(row))
        rows.append(row)
        print(f"{name:45s} {row['flags']}", flush=True)
    keys = sorted({k for row in rows for k in row}, key=lambda k: (k not in rows[0], k))
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    with args.out_json.open("w") as fh:
        json.dump({"provenance": prov, "rows": rows}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
