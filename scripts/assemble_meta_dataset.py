#!/usr/bin/env python3
"""Assemble the meta-learning table: one row per successful run (T11).

Walks results/{strategy}/{combo}/{dataset}/{fl_algo}/rep_{r}/ and, for each run
that passed the completion gate (T03: a `_SUCCESS` sentinel), emits one row of
features + targets to meta_dataset.csv. Incomplete/failed runs are excluded, and
a run whose targets can't be computed is dropped with a warning (so no NaN
targets). Re-runnable and idempotent over a growing results/ tree.

Features
  identity            strategy (+ strategy_* one-hot), node counts, num_workers,
                      n_workers_joined, dataset, fl_algo (+ fl_algo_* one-hot), repeat
  FL hyperparameters  learning_rate, batch_size, patience, delta, local_epochs (T07;
                      imputed 0 for Centralized, T46)
  dataset meta        task, is_classification, n_samples, n_features, n_classes,
                      is_categorical (T08 option B — raw architecture held fixed, not used directly)
  model architecture  total_parameters, n_layers, mean_layer_width, max_layer_width,
                      weight_decay — from the dataset's HPO config; size/shape
                      scalars plus weight decay, not the raw per-layer unit list.
  partition           strategy, alpha, distribution_percentage,
                      feat_entropy_{mean,min,max,std} (cross-worker split entropy)
  worker compute      mean/min/max/std/cv of per-worker epochs-per-second from the
                      machine benchmark, over the participating workers, joined by
                      (node, vmid)

Three columns count workers and mean different things: num_workers is the intended count
from division.json; n_workers is the number of worker lines in workers.txt; and
n_workers_joined counts the master's `new_worker` events, i.e. the workers that actually
registered and were eligible for the aggregation pool. n_workers_joined < num_workers marks
a short-pool run.

local_epochs is 0 for every Centralized row by construction (T46) — a sentinel for
"this algorithm has no local-training concept," not a measured zero. Do not use it as
a multiplicative or log-scale compute term without gating on fl_algo; a consumer that
drops fl_algo (e.g. after a groupby or column subset) cannot recover which zeros are
structural.

Targets (master log_0.jsonl, single clock; T09)
  performance         best validation main metric (mcc↑ clf / smape↓ reg). NB: the
                      regression metric is logged under the key `mape` but is actually
                      SMAPE (FederatedABC.smape); `main_metric` reports that key verbatim.
  total_time_s        master start→end delta
  comm_bytes_{sent,recv,total}   Σ payload_size of the master's send/recv events
  n_epochs            rounds until early stop — an OUTCOME, not a feature; exclude it
                      from the predictor set (leakage) unless modelling it as a target.
  compute_time_{total,max}_s, comm_time_{total,max}_s, serial_time_total_s, validation_time_s,
  comm_skew_clamped   time decomposition from log_0.jsonl plus worker_N/log_M.jsonl
                      (flexfl.builtins.event_metrics, the pairing Results uses): worker work,
                      message transit and encode/decode seconds, every interval clipped to the
                      master start-to-end window, _total summed over workers, _max the busiest
                      worker. comm_time_* pairs a master and a worker clock; comm_skew_clamped
                      counts pairs whose negative duration was clamped to 0. Empty, with a
                      warning, when a run has no worker logs or no work inside the window.
                      Outcomes, like n_epochs: not predictors.
"""
import argparse
from collections import Counter
import csv
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_meta_features import DEFAULT_METADATA_DIR, architecture_features, meta_features  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from flexfl.builtins.event_metrics import decomposition  # noqa: E402

DEFAULT_HPO_DIR = Path(__file__).resolve().parent.parent / "results/hyperparameter_optimization"

DECOMPOSITION_COLUMNS = [
    "compute_time_total_s", "compute_time_max_s", "comm_time_total_s", "comm_time_max_s",
    "serial_time_total_s", "validation_time_s", "comm_skew_clamped",
]

COLUMNS = [
    "strategy", "strategy_iid", "strategy_non_iid", "strategy_dirichlet",
    "combo", "n_atnog_test1", "n_hobbit", "n_samwise", "num_workers", "n_workers_joined",
    "dataset", "fl_algo",
    "fl_algo_CentralizedSync", "fl_algo_CentralizedAsync", "fl_algo_DecentralizedSync", "fl_algo_DecentralizedAsync",
    "repeat",
    "learning_rate", "batch_size", "patience", "delta", "local_epochs",
    "task", "is_classification", "is_categorical", "n_samples", "n_features", "n_classes",
    "total_parameters", "n_layers", "mean_layer_width", "max_layer_width", "weight_decay",
    "alpha", "distribution_percentage",
    "feat_entropy_mean", "feat_entropy_min", "feat_entropy_max", "feat_entropy_std",
    "n_workers", "n_workers_benchmarked",
    "worker_rate_mean", "worker_rate_min", "worker_rate_max", "worker_rate_std", "worker_rate_cv",
    "performance", "main_metric", "total_time_s",
    "comm_bytes_sent", "comm_bytes_recv", "comm_bytes_total", "n_epochs",
    *DECOMPOSITION_COLUMNS,
]

ALGO_ALIASES = {
    "centralizedsync": "CentralizedSync", "cs": "CentralizedSync",
    "centralizedasync": "CentralizedAsync", "ca": "CentralizedAsync",
    "decentralizedsync": "DecentralizedSync", "ds": "DecentralizedSync",
    "decentralizedasync": "DecentralizedAsync", "da": "DecentralizedAsync",
}
CENTRALIZED_ALGOS = {"CentralizedSync", "CentralizedAsync"}


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


EVENT_FIELDS = {
    "start": ("timestamp",), "end": ("timestamp",),
    "send": ("sender", "receiver", "payload_size", "timestamp"),
    "recv": ("sender", "receiver", "payload_size", "timestamp"),
    "encode": ("time", "timestamp"), "decode": ("time", "timestamp"),
    "working_start": ("timestamp",), "working_end": ("timestamp",), "failure": ("timestamp",),
    "validation_start": ("timestamp",), "validation_end": ("timestamp",),
}
ANOMALY_WARNINGS = (
    ("n_unmatched_comms", "send/recv events unmatched"),
    ("n_orphan_comms", "master send/recv events address an absent worker log"),
    ("n_unclosed_work_logs", "worker logs with unpaired working_start/end"),
    ("n_unmatched_validations", "validation_start/end events unpaired"),
)


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    events, bad = [], 0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    return events, bad


def well_formed(event) -> bool:
    if not isinstance(event, dict) or not isinstance(event.get("event"), str):
        return False
    return all(
        isinstance(event.get(field), (int, float)) and not isinstance(event.get(field), bool)
        for field in EVENT_FIELDS.get(event["event"], ())
    )


def time_decomposition(rep_dir: Path, events: list[dict]) -> tuple[dict, str | None, list[str]]:
    empty = dict.fromkeys(DECOMPOSITION_COLUMNS)
    master_log = sorted(rep_dir.rglob("log_0.jsonl"))[0]
    master = [e for e in events if well_formed(e)]
    notes = []
    if len(master) < len(events):
        notes.append(f"{len(events) - len(master)} malformed records skipped in {master_log}")
    logs, log2node = {0: master}, {0: 0}
    for path in sorted(master_log.parent.glob("worker_*/log_*.jsonl")):
        log_id = int(path.name.split("_")[1].split(".")[0])
        if log_id in logs:
            notes.append(f"duplicate worker log id {log_id}, ignored: {path}")
            continue
        parsed, bad = read_jsonl(path)
        worker_events = [e for e in parsed if well_formed(e)]
        bad += len(parsed) - len(worker_events)
        if bad:
            notes.append(f"{bad} malformed records skipped in {path}")
        logs[log_id] = worker_events
        log2node[log_id] = int(path.parent.name.split("_")[1])
    if len(logs) == 1:
        return empty, "no worker logs", notes
    t0 = next(e["timestamp"] for e in events if e.get("event") == "start")
    t1 = [e for e in events if e.get("event") == "end"][-1]["timestamp"]
    split = decomposition(logs, log2node, t0, t1)
    for key, label in ANOMALY_WARNINGS:
        if split[key]:
            notes.append(f"{split[key]} {label} in {rep_dir}")
    if split["n_work_intervals_in_window"] == 0 and split["n_work_events_in_window"] == 0:
        return empty, "no work inside the master window", notes
    return {k: split[k] for k in DECOMPOSITION_COLUMNS}, None, notes


def compute_targets(events: list[dict], is_classification: bool) -> dict | None:
    starts = [e for e in events if e.get("event") == "start"]
    ends = [e for e in events if e.get("event") == "end"]
    epochs = [e for e in events if e.get("event") == "epoch"]
    if not starts or not ends or not epochs:
        return None
    main = "mcc" if is_classification else "mape"
    vals = [v for e in epochs if isinstance((v := e.get(main)), (int, float)) and math.isfinite(v)]
    if not vals:
        return None
    perf = max(vals) if is_classification else min(vals)
    if not math.isfinite(perf):
        return None
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
    lines = [ln.strip() for ln in workers_txt.read_text().splitlines()
             if ln.strip() and not ln.startswith("#")]
    entries = [ln.split() for ln in lines]
    worker_entries = entries[1:]  # line 1 is the anchor (frodo)
    rates = []
    legacy = False
    for fields in worker_entries:
        if len(fields) < 3:
            legacy = True
            continue
        node, vmid = fields[1], fields[2]
        bf = benchmark_dir / f"machine_benchmark_{node}_{vmid}.json"
        if not bf.exists():
            continue
        results = load_json(bf).get("results", {})
        model_rates = [r for m in results.values()
                       if isinstance((r := m.get("avg_epochs_per_second")), (int, float)) and math.isfinite(r)]
        if model_rates:
            rates.append(statistics.fmean(model_rates))
    legacy_key = {"_legacy_workers_txt": str(workers_txt)} if legacy else {}
    if not rates or len(rates) < len(worker_entries):
        return {**empty, "n_workers": len(worker_entries),
                "n_workers_benchmarked": len(rates), **legacy_key}
    mean = statistics.fmean(rates)
    std = statistics.pstdev(rates) if len(rates) > 1 else 0.0
    return {
        "n_workers": len(worker_entries),
        "n_workers_benchmarked": len(rates),
        "worker_rate_mean": mean,
        "worker_rate_min": min(rates),
        "worker_rate_max": max(rates),
        "worker_rate_std": std,
        "worker_rate_cv": (std / mean) if mean else None,
        **legacy_key,
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


def assemble(results_dir: Path, metadata_dir: Path, hpo_dir: Path) -> tuple[list[dict], list[str]]:
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
        if mf["n_features"] is None or mf["n_classes"] is None:
            warnings.append(f"missing n_features/n_classes for {dataset}, skipped: {rep_dir}")
            continue

        hpo_file = hpo_dir / f"{dataset}.json"
        if not hpo_file.exists():
            warnings.append(f"no HPO config for {dataset}, skipped: {rep_dir}")
            continue
        try:
            af = architecture_features(load_json(hpo_file), mf["n_features"], mf["n_classes"])
        except (KeyError, TypeError, ValueError, statistics.StatisticsError) as e:
            warnings.append(f"malformed HPO config for {dataset} ({e}), skipped: {rep_dir}")
            continue

        events = read_master_events(rep_dir)
        targets = compute_targets(events, mf["is_classification"])
        if targets is None:
            warnings.append(f"targets uncomputable (missing start/end/epoch), skipped: {rep_dir}")
            continue

        decomposition_columns, null_cause, decomposition_notes = time_decomposition(rep_dir, events)
        warnings.extend(decomposition_notes)
        if null_cause is not None:
            warnings.append(f"time decomposition unavailable ({null_cause}): {rep_dir}")

        row = {
            "strategy": division.get("strategy", strategy),
            "combo": combo,
            **parse_combo(combo),
            "num_workers": division.get("num_workers"),
            "n_workers_joined": sum(1 for e in events if e.get("event") == "new_worker"),
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
            "total_parameters": af["total_parameters"],
            "n_layers": af["n_layers"],
            "mean_layer_width": af["mean_layer_width"],
            "max_layer_width": af["max_layer_width"],
            "weight_decay": af["weight_decay"],
            "alpha": division.get("alpha"),
            "distribution_percentage": division.get("distribution_percentage"),
            "feat_entropy_mean": entropy.get("mean"),
            "feat_entropy_min": entropy.get("min"),
            "feat_entropy_max": entropy.get("max"),
            "feat_entropy_std": entropy.get("std"),
            **worker_compute(rep_dir.parent.parent.parent / "workers.txt", benchmark_dir),
            **targets,
            **decomposition_columns,
            "_decomposition_null_cause": null_cause,
        }
        canonical_fl_algo = ALGO_ALIASES.get(row["fl_algo"].lower())
        if canonical_fl_algo is None:
            warnings.append(f"unrecognized fl_algo {row['fl_algo']!r}, skipped: {rep_dir}")
            continue
        if canonical_fl_algo in CENTRALIZED_ALGOS and row["local_epochs"] is None:
            row["local_epochs"] = 0
        elif row["local_epochs"] is None:
            warnings.append(f"local_epochs unrecorded for {rep_dir} (fl_algo={row['fl_algo']})")
        if all(row[k] is None for k in ("learning_rate", "batch_size", "patience", "delta")):
            warnings.append(f"no FL hyperparameters recorded for {rep_dir}")
        for algo in ("CentralizedSync", "CentralizedAsync", "DecentralizedSync", "DecentralizedAsync"):
            row[f"fl_algo_{algo}"] = int(canonical_fl_algo == algo)
        for strat in ("iid", "non_iid", "dirichlet"):
            row[f"strategy_{strat}"] = int(row["strategy"] == strat)
        if sum(row[f"strategy_{s}"] for s in ("iid", "non_iid", "dirichlet")) != 1:
            warnings.append(f"unrecognized strategy {row['strategy']!r}, skipped: {rep_dir}")
            continue
        legacy_workers_txt = row.get("_legacy_workers_txt")
        if legacy_workers_txt is not None:
            warnings.append(f"legacy IP-only workers.txt, worker compute skipped: {legacy_workers_txt}")
        if row.get("n_workers") and row.get("n_workers_benchmarked", 0) < row["n_workers"]:
            warnings.append(
                f"worker compute features incomplete for {rep_dir}: "
                f"{row['n_workers_benchmarked']}/{row['n_workers']} workers benchmarked "
                f"(missing machine_benchmark_<node>_<vmid>.json for some workers)"
            )
        rows.append(row)
    return rows, warnings


def main():
    p = argparse.ArgumentParser(description="Assemble the per-run meta-learning table (T11).")
    p.add_argument("--results-dir", type=Path, default=Path("results"))
    p.add_argument("--metadata-dir", type=Path, default=DEFAULT_METADATA_DIR)
    p.add_argument("--hpo-dir", type=Path, default=DEFAULT_HPO_DIR)
    p.add_argument("--out", type=Path, default=Path("results/meta_dataset.csv"))
    args = p.parse_args()

    rows, warnings = assemble(args.results_dir, args.metadata_dir, args.hpo_dir)
    for w in warnings:
        print(f"  ! {w}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.out} ({len(warnings)} skipped).")
    null_causes = Counter(r["_decomposition_null_cause"] for r in rows if r["_decomposition_null_cause"])
    if null_causes:
        detail = ", ".join(f"{cause}: {count}" for cause, count in sorted(null_causes.items()))
        print(f"Time decomposition unavailable for {sum(null_causes.values())} of {len(rows)} rows ({detail}).")


if __name__ == "__main__":
    main()
