import argparse
import csv
import hashlib
import json
import subprocess
from importlib.metadata import version
from pathlib import Path

import numpy as np
from datasets import load_dataset
from huggingface_hub import HfApi
from scipy import stats
from sklearn.preprocessing import LabelEncoder

from flexfl.datasets.Benchmark import SENTINEL, Benchmark, drop_sentinel_rows

SENTINELS = {-99999.0, -9999.0, -999.0, -99.0, 999.0, 9999.0, 99999.0}


def load_splits(name, revision, drop_sentinel=False):
    df = load_dataset("inria-soda/tabular-benchmark", name, revision=revision)[
        "train"
    ].to_pandas()
    x = df.iloc[:, :-1].to_numpy(dtype=np.float64)
    y = df.iloc[:, -1].to_numpy()
    if drop_sentinel:
        x, y = drop_sentinel_rows(x, y)
    if name.startswith("clf_"):
        y = LabelEncoder().fit_transform(y)
    arrays = Benchmark(data_name=name).split_data(x, y, 0.2, 0.2)
    keys = ("x_train", "y_train", "x_val", "y_val", "x_test", "y_test")
    return dict(zip(keys, arrays))


def top_value(col):
    vals, counts = np.unique(col, return_counts=True)
    i = int(np.argmax(counts))
    return float(vals[i]), counts[i] / col.size, vals.size


def audit(name, data, tier20):
    xtr, xva, xte = data["x_train"], data["x_val"], data["x_test"]
    ytr = data["y_train"]
    yall = np.concatenate([data["y_train"], data["y_val"], data["y_test"]])
    xall = np.concatenate([xtr, xva, xte])
    clf = name.startswith("clf_")
    r = {"dataset": name, "tier20": name in tier20, "task": "clf" if clf else "reg"}
    r["n_train"], r["n_val"], r["n_test"] = len(xtr), len(xva), len(xte)
    r["n_feat"] = xtr.shape[1]
    r["n_nonfinite"] = int(
        (~np.isfinite(xall)).sum() + (~np.isfinite(yall.astype(np.float64))).sum()
    )
    r["n_sentinel_cells"] = int((xall == SENTINEL).sum())
    r["n_all_sentinel_rows"] = int(np.all(xall == SENTINEL, axis=1).sum())

    mean = xtr.mean(axis=0)
    std = xtr.std(axis=0)
    const = std == 0
    r["n_const"] = int(const.sum())
    scale = np.where(const, 1.0, std)

    near_const, binary, sentinel_hits = 0, 0, []
    for j in range(xtr.shape[1]):
        v, frac, nuniq = top_value(xtr[:, j])
        if nuniq <= 2:
            binary += 1
        if not const[j] and frac >= 0.99:
            near_const += 1
        if nuniq > 2 and frac >= 0.01:
            z = abs(v - mean[j]) / scale[j]
            is_edge = v in (xtr[:, j].min(), xtr[:, j].max())
            if v in SENTINELS or (is_edge and z > 4):
                sentinel_hits.append(f"f{j}={v:g}({frac:.1%},z={z:.1f})")
    r["n_near_const"] = near_const
    r["n_binary"] = binary
    r["n_sentinel_cand"] = len(sentinel_hits)
    r["sentinel_examples"] = ";".join(sentinel_hits[:4])

    z_all = np.abs((xall - mean) / scale)
    z_feat = z_all.max(axis=0)
    r["max_abs_z"] = float(z_feat.max())
    r["worst_feat"] = int(z_feat.argmax())
    r["n_feat_z_gt10"] = int((z_feat > 10).sum())
    r["n_feat_z_gt50"] = int((z_feat > 50).sum())
    r["frac_cells_z_gt10"] = float((z_all > 10).mean())

    cont = [
        j
        for j in range(xtr.shape[1])
        if not const[j] and len(np.unique(xtr[:, j])) > 10
    ]
    if cont:
        kurt = stats.kurtosis(xtr[:, cont], axis=0, fisher=True, bias=False)
        skew = stats.skew(xtr[:, cont], axis=0, bias=False)
        r["n_continuous"] = len(cont)
        r["max_excess_kurtosis"] = float(np.nanmax(kurt))
        r["n_kurt_gt20"] = int((kurt > 20).sum())
        r["n_abs_skew_gt5"] = int((np.abs(skew) > 5).sum())
    else:
        r["n_continuous"] = 0
        r["max_excess_kurtosis"] = 0.0
        r["n_kurt_gt20"] = 0
        r["n_abs_skew_gt5"] = 0

    lo, hi = xtr.min(axis=0), xtr.max(axis=0)
    xvt = np.concatenate([xva, xte])
    out_range = ((xvt < lo) | (xvt > hi)).mean(axis=0)
    r["max_frac_outside_train_range"] = float(out_range.max())

    _, inv, counts = np.unique(xtr, axis=0, return_inverse=True, return_counts=True)
    r["frac_dup_rows_train"] = float(1 - len(counts) / len(xtr))
    if clf and len(counts) < len(xtr):
        inv = inv.ravel()
        conflict = 0
        for g in np.where(counts > 1)[0]:
            if len(np.unique(ytr[inv == g])) > 1:
                conflict += counts[g]
        r["frac_dup_label_conflict"] = float(conflict / len(xtr))
    else:
        r["frac_dup_label_conflict"] = 0.0
    _, col_counts = np.unique(xtr.T, axis=0, return_counts=True)
    r["n_dup_cols"] = int(xtr.shape[1] - len(col_counts))

    yf = ytr.astype(np.float64)
    corrs = []
    for j in range(xtr.shape[1]):
        if const[j]:
            continue
        if clf and len(np.unique(ytr)) > 2:
            continue
        c = np.corrcoef(xtr[:, j], yf)[0, 1]
        if np.isfinite(c):
            corrs.append(abs(c))
    r["max_abs_corr_feat_y"] = float(max(corrs)) if corrs else float("nan")

    if clf:
        _, cc = np.unique(yall, return_counts=True)
        r["n_classes"] = int(cc.size)
        r["min_class_frac"] = float(cc.min() / cc.sum())
        r["imbalance_ratio"] = float(cc.max() / cc.min())
    else:
        y = yall.astype(np.float64)
        r["y_mean"], r["y_std"] = float(y.mean()), float(y.std())
        r["y_min"], r["y_max"] = float(y.min()), float(y.max())
        r["y_median"] = float(np.median(y))
        r["y_skew"] = float(stats.skew(y, bias=False))
        r["y_excess_kurtosis"] = float(stats.kurtosis(y, bias=False))
        r["y_max_z"] = float(np.abs((y - y.mean()) / (y.std() or 1)).max())
        r["y_top_value_frac"] = top_value(y)[1]
        if y.min() >= 0:
            r["y_log1p_skew"] = float(stats.skew(np.log1p(y), bias=False))
        else:
            r["y_log1p_skew"] = float("nan")
    return r


def flags(r):
    f = []
    if r["n_nonfinite"]:
        f.append("nonfinite")
    if r["n_const"]:
        f.append("constant_features")
    if r["n_feat_z_gt50"]:
        f.append("extreme_outliers_z50")
    elif r["n_feat_z_gt10"]:
        f.append("outliers_z10")
    if r["n_kurt_gt20"]:
        f.append("heavy_tails")
    if r["n_sentinel_cand"]:
        f.append("sentinel_candidates")
    if r["n_all_sentinel_rows"]:
        f.append("all_sentinel_rows")
    if r["frac_dup_rows_train"] > 0.05:
        f.append("many_duplicate_rows")
    if r["frac_dup_label_conflict"] > 0.01:
        f.append("duplicate_label_conflicts")
    if r["n_dup_cols"]:
        f.append("duplicate_columns")
    if np.isfinite(r["max_abs_corr_feat_y"]) and r["max_abs_corr_feat_y"] > 0.98:
        f.append("leak_candidate")
    if r["max_frac_outside_train_range"] > 0.01:
        f.append("split_shift")
    if r["task"] == "clf" and r["imbalance_ratio"] > 10:
        f.append("class_imbalance")
    if r["task"] == "reg":
        if abs(r["y_skew"]) > 2:
            f.append("skewed_target")
        if r["y_max_z"] > 10:
            f.append("target_outliers")
    return f


def provenance():
    root = Path(__file__).resolve().parent.parent
    sources = (
        "scripts/audit_datasets.py",
        "scripts/audit_central_sanity.py",
        "src/flexfl/datasets/Benchmark.py",
        "src/flexfl/builtins/DatasetABC.py",
    )
    hf_dataset = "inria-soda/tabular-benchmark"
    return {
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            ).strip()
        ),
        "sources_sha256": {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in sources
        },
        "hf_dataset": hf_dataset,
        "hf_revision": HfApi().dataset_info(hf_dataset).sha,
        "val_size": 0.2,
        "test_size": 0.2,
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
    names = [
        line.strip() for line in args.names.read_text().splitlines() if line.strip()
    ]
    tier20 = {
        line.strip() for line in args.tier20.read_text().splitlines() if line.strip()
    }
    prov = provenance()
    rows = []
    for name in names:
        data = load_splits(name, prov["hf_revision"], drop_sentinel=False)
        r = audit(name, data, tier20)
        r["flags"] = ",".join(flags(r))
        rows.append(r)
        print(f"{name:45s} {r['flags']}", flush=True)
    keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in rows[0], k))
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
