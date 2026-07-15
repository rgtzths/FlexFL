#!/usr/bin/env python3
"""Assemble the meta-learning table: one row per successful run (T11).

Walks results/{strategy}/{combo}/{dataset}/{fl_algo}/rep_{r}/ and, for each run
that passed the completion gate (T03: a `_SUCCESS` sentinel), emits one row of
features + targets to meta_dataset.csv. Incomplete/failed runs are excluded, and
a run whose targets can't be computed is dropped with a warning (so no NaN
targets). Re-runnable and idempotent over a growing results/ tree.

Features
  identity            strategy, node counts, num_workers, dataset, fl_algo, repeat
  FL hyperparameters  learning_rate, batch_size, patience, delta, local_epochs (T07)
  dataset meta        task, is_classification, n_samples, n_features, n_classes,
                      is_categorical (T08 option B — architecture held fixed)
  partition           strategy, alpha, distribution_percentage,
                      feat_entropy_{mean,min,max,std} (cross-worker split entropy)
  worker compute      mean/min/max/std/cv of per-worker epochs-per-second from the
                      machine benchmark, over the participating workers
Targets (master log_0.jsonl, single clock; T09)
  performance         best validation main metric (mcc↑ clf / smape↓ reg). NB: the
                      regression metric is logged under the key `mape` but is actually
                      SMAPE (FederatedABC.smape); `main_metric` reports that key verbatim.
  total_time_s        master start→end delta
  comm_bytes_{sent,recv,total}   Σ payload_size of the master's send/recv events
  n_epochs            rounds until early stop — an OUTCOME, not a feature; exclude it
                      from the predictor set (leakage) unless modelling it as a target.
"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_meta_features import DEFAULT_METADATA_DIR, meta_features  # noqa: E402

COLUMNS = [
    "strategy", "combo", "n_atnog_test1", "n_hobbit", "n_samwise", "num_workers",
    "dataset", "fl_algo", "repeat",
    "learning_rate", "batch_size", "patience", "delta", "local_epochs",
    "task", "is_classification", "is_categorical", "n_samples", "n_features", "n_classes",
    "alpha", "distribution_percentage",
    "feat_entropy_mean", "feat_entropy_min", "feat_entropy_max", "feat_entropy_std",
    "n_workers", "n_workers_benchmarked",
    "worker_rate_mean", "worker_rate_min", "worker_rate_max", "worker_rate_std", "worker_rate_cv",
    "performance", "main_metric", "total_time_s",
    "comm_bytes_sent", "comm_bytes_recv", "comm_bytes_total", "n_epochs",
]


def load_json(path: Path):
    return json.loads(path.read_text())


def parse_combo(combo: str) -> dict:
    # atnog-test1_{n1}_hobbit_{n2}_samwise_{n3}
    parts = combo.split("_")
    out = {}
    for i, token in enumerate(parts):
        if token in ("atnog-test1", "hobbit", "samwise") and i + 1 < len(parts):
            out[token] = int(parts[i + 1])
    return {
        "n_atnog_test1": out.get("atnog-test1"),
        "n_hobbit": out.get("hobbit"),
        "n_samwise": out.get("samwise"),
    }


def read_master_events(rep_dir: Path) -> list[dict]:
    logs = sorted(rep_dir.rglob("log_0.jsonl"))
    if not logs:
        return []
    events = []
    for line in logs[0].read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def compute_targets(events: list[dict], is_classification: bool) -> dict | None:
    starts = [e for e in events if e.get("event") == "start"]
    ends = [e for e in events if e.get("event") == "end"]
    epochs = [e for e in events if e.get("event") == "epoch"]
    if not starts or not ends or not epochs:
        return None
    main = "mcc" if is_classification else "mape"
    vals = [e[main] for e in epochs if isinstance(e.get(main), (int, float))]
    if not vals:
        return None
    perf = max(vals) if is_classification else min(vals)
    sent = sum(e.get("payload_size", 0) for e in events if e.get("event") == "send")
    recv = sum(e.get("payload_size", 0) for e in events if e.get("event") == "recv")
    return {
        "performance": perf,
        "main_metric": main,
        "total_time_s": ends[-1]["timestamp"] - starts[0]["timestamp"],
        "comm_bytes_sent": sent,
        "comm_bytes_recv": recv,
        "comm_bytes_total": sent + recv,
        "n_epochs": len(epochs),
    }


def worker_compute(workers_txt: Path, benchmark_dir: Path) -> dict:
    empty = {
        "n_workers": None, "n_workers_benchmarked": 0,
        "worker_rate_mean": None, "worker_rate_min": None, "worker_rate_max": None,
        "worker_rate_std": None, "worker_rate_cv": None,
    }
    if not workers_txt.exists():
        return empty
    ips = [ln.strip() for ln in workers_txt.read_text().splitlines()
           if ln.strip() and not ln.startswith("#")]
    worker_ips = ips[1:]  # line 1 is the anchor (frodo)
    rates = []
    for ip in worker_ips:
        bf = benchmark_dir / f"machine_benchmark_{ip}.json"
        if not bf.exists():
            continue
        results = load_json(bf).get("results", {})
        model_rates = [m["avg_epochs_per_second"] for m in results.values()
                       if isinstance(m.get("avg_epochs_per_second"), (int, float))]
        if model_rates:
            rates.append(statistics.fmean(model_rates))
    if not rates:
        return {**empty, "n_workers": len(worker_ips)}
    mean = statistics.fmean(rates)
    std = statistics.pstdev(rates) if len(rates) > 1 else 0.0
    return {
        "n_workers": len(worker_ips),
        "n_workers_benchmarked": len(rates),
        "worker_rate_mean": mean,
        "worker_rate_min": min(rates),
        "worker_rate_max": max(rates),
        "worker_rate_std": std,
        "worker_rate_cv": (std / mean) if mean else None,
    }


def fl_hyperparameters(rep_dir: Path) -> dict:
    hp_file = rep_dir / "hyperparameters.json"
    hp = load_json(hp_file) if hp_file.exists() else {}
    if not hp:  # fallback to the master's recorded args
        args = sorted(rep_dir.rglob("args.json"))
        if args:
            a = load_json(args[0])
            hp = {k: a.get(k) for k in ("learning_rate", "batch_size", "patience", "delta", "local_epochs")
                  if a.get(k) is not None}
    return {
        "learning_rate": hp.get("learning_rate"),
        "batch_size": hp.get("batch_size"),
        "patience": hp.get("patience"),
        "delta": hp.get("delta"),
        "local_epochs": hp.get("local_epochs"),
    }


def assemble(results_dir: Path, metadata_dir: Path) -> tuple[list[dict], list[str]]:
    benchmark_dir = results_dir / "benchmark"
    rows, warnings = [], []
    for success in sorted(results_dir.rglob("_SUCCESS")):
        rep_dir = success.parent
        rel = rep_dir.relative_to(results_dir).parts
        if len(rel) < 5 or not rel[-1].startswith("rep_"):
            warnings.append(f"unexpected path, skipped: {rep_dir}")
            continue
        strategy, combo, dataset, fl_algo, rep = rel[-5], rel[-4], rel[-3], rel[-2], rel[-1]

        division = {}
        div_file = rep_dir.parent.parent / "division.json"
        if div_file.exists():
            division = load_json(div_file)
        entropy = division.get("worker_feature_entropy", {}) or {}

        meta_file = metadata_dir / f"{dataset}.json"
        if not meta_file.exists():
            warnings.append(f"no metadata for {dataset}, skipped: {rep_dir}")
            continue
        mf = meta_features(load_json(meta_file))

        events = read_master_events(rep_dir)
        targets = compute_targets(events, mf["is_classification"])
        if targets is None:
            warnings.append(f"targets uncomputable (missing start/end/epoch), skipped: {rep_dir}")
            continue

        row = {
            "strategy": division.get("strategy", strategy),
            "combo": combo,
            **parse_combo(combo),
            "num_workers": division.get("num_workers"),
            "dataset": dataset,
            "fl_algo": fl_algo,
            "repeat": int(rep.split("_")[1]),
            **fl_hyperparameters(rep_dir),
            "task": mf["task"],
            "is_classification": mf["is_classification"],
            "is_categorical": "_cat_" in dataset,
            "n_samples": mf["n_samples"],
            "n_features": mf["n_features"],
            "n_classes": mf["n_classes"],
            "alpha": division.get("alpha"),
            "distribution_percentage": division.get("distribution_percentage"),
            "feat_entropy_mean": entropy.get("mean"),
            "feat_entropy_min": entropy.get("min"),
            "feat_entropy_max": entropy.get("max"),
            "feat_entropy_std": entropy.get("std"),
            **worker_compute(rep_dir.parent.parent.parent / "workers.txt", benchmark_dir),
            **targets,
        }
        if row.get("n_workers") and row.get("n_workers_benchmarked", 0) < row["n_workers"]:
            warnings.append(
                f"worker compute features incomplete for {rep_dir}: "
                f"{row['n_workers_benchmarked']}/{row['n_workers']} workers benchmarked "
                f"(likely benchmark/run IP mismatch)"
            )
        rows.append(row)
    return rows, warnings


def main():
    p = argparse.ArgumentParser(description="Assemble the per-run meta-learning table (T11).")
    p.add_argument("--results-dir", type=Path, default=Path("results"))
    p.add_argument("--metadata-dir", type=Path, default=DEFAULT_METADATA_DIR)
    p.add_argument("--out", type=Path, default=Path("results/meta_dataset.csv"))
    args = p.parse_args()

    rows, warnings = assemble(args.results_dir, args.metadata_dir)
    for w in warnings:
        print(f"  ! {w}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.out} ({len(warnings)} skipped).")


if __name__ == "__main__":
    main()
