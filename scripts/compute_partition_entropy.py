#!/usr/bin/env python3
"""Cross-worker feature-split entropy meta-features (T08).

For each feature: quantile-bin its values over the pooled data; for each bin,
measure the entropy of how that bin's samples are distributed across the N
workers, normalized so 1.0 = perfectly even (IID-like) split and lower = the bin
is concentrated on a few workers. Average over bins gives a per-feature value;
those are aggregated (mean/min/max/std) into a few scalars that quantify how
heterogeneous the partition is — which is what varies with iid/non_iid/dirichlet.

Reads the per-worker partitions data/<name>/node_{1..N}/x_train.npy and, with
--update-json, merges the result under "worker_feature_entropy" into division.json.
Runs at division time (while the node_* partitions still exist).
"""
import argparse
import json
from pathlib import Path

import numpy as np


def numeric_columns(global_x: np.ndarray) -> list[int]:
    """Indices of columns castable to float (drops categorical/string columns)."""
    keep = []
    for j in range(global_x.shape[1]):
        try:
            global_x[:, j].astype(float)
            keep.append(j)
        except (ValueError, TypeError):
            continue
    return keep


def per_feature_split_entropy(worker_feats: list[np.ndarray], n_bins: int = 10) -> list[float]:
    n_workers = len(worker_feats)
    if n_workers < 2:
        return []
    log_w = np.log(n_workers)
    n_features = worker_feats[0].shape[1]
    pooled = np.concatenate(worker_feats, axis=0)
    entropies = []
    for j in range(n_features):
        col = pooled[:, j]
        edges = np.unique(np.quantile(col, np.linspace(0.0, 1.0, n_bins + 1)))
        if edges.size < 2:
            continue  # constant feature — carries no split information
        counts = np.zeros((n_workers, edges.size - 1))
        for w, wf in enumerate(worker_feats):
            counts[w], _ = np.histogram(wf[:, j], bins=edges)
        bin_totals = counts.sum(axis=0)
        bin_entropies = []
        for b in range(counts.shape[1]):
            if bin_totals[b] <= 0:
                continue
            p = counts[:, b] / bin_totals[b]
            p = p[p > 0]
            h = -np.sum(p * np.log(p)) / log_w  # normalized to [0, 1]
            bin_entropies.append(h)
        if bin_entropies:
            entropies.append(float(np.mean(bin_entropies)))
    return entropies


def load_worker_features(data_dir: Path, num_workers: int) -> list[np.ndarray]:
    raw = []
    for w in range(1, num_workers + 1):
        path = data_dir / f"node_{w}" / "x_train.npy"
        x = np.load(path, allow_pickle=True)
        x = np.asarray(x)
        if x.ndim == 1:
            x = x.reshape(-1, 1)
        raw.append(x)
    pooled = np.concatenate(raw, axis=0)
    keep = numeric_columns(pooled)
    if not keep:
        raise ValueError("no numeric feature columns found in partitions")
    return [wf[:, keep].astype(float) for wf in raw]


def summarize(entropies: list[float], n_bins: int) -> dict:
    if not entropies:
        return {k: None for k in ("mean", "min", "max", "std")} | {"n_features_used": 0, "n_bins": n_bins}
    arr = np.array(entropies)
    return {
        "mean": float(arr.mean()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "std": float(arr.std()),
        "n_features_used": int(arr.size),
        "n_bins": n_bins,
    }


def main():
    p = argparse.ArgumentParser(description="Cross-worker feature-split entropy meta-features.")
    p.add_argument("--data-dir", required=True, help="data/<dataset> holding node_{1..N}/")
    p.add_argument("--num-workers", type=int, required=True)
    p.add_argument("--n-bins", type=int, default=10)
    p.add_argument("--update-json", help="Merge result under 'worker_feature_entropy' into this JSON")
    args = p.parse_args()

    worker_feats = load_worker_features(Path(args.data_dir), args.num_workers)
    result = summarize(per_feature_split_entropy(worker_feats, args.n_bins), args.n_bins)

    if args.update_json:
        path = Path(args.update_json)
        doc = json.loads(path.read_text()) if path.exists() else {}
        doc["worker_feature_entropy"] = result
        path.write_text(json.dumps(doc, indent=2))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
