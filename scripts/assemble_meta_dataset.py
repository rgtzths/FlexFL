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
  epoch cap           epoch_cap: the global epoch cap the run trained under, the
                      `epochs` the master recorded in the args.json beside its
                      log_0.jsonl. A run whose args.json has no `epochs` key is
                      dropped with a warning, unless --legacy-epoch-cap N assigns
                      N to such runs (runs made before the cap was recorded
                      trained under the old default of 10).
                      A recorded value that is not a positive int, and an
                      unreadable args.json, always drop the run (T056).
  early-stop rule     early_stop_on, min_epochs: what the patience window watched
                      ("loss", delta as a relative improvement, or "metric", the
                      main metric with an absolute delta) and the first epoch at
                      which a stop could fire, as recorded in the same args.json.
                      A run that recorded neither is dropped with a warning,
                      unless --legacy-early-stop-rule assigns "metric" and 0, the
                      rule every run used before it was recorded. A run that
                      recorded only one of the two, or a pair that is not a known
                      rule and a non-negative int, always drops (T059).
  dataset meta        task, is_classification, n_samples, n_features, n_classes,
                      is_categorical (T08 option B — raw architecture held
                      fixed, not used directly)
  model architecture  total_parameters, n_layers, mean_layer_width, max_layer_width,
                      weight_decay — from the dataset's HPO config; size/shape
                      scalars plus weight decay, not the raw per-layer unit list.
  partition           strategy, alpha, distribution_percentage,
                      feat_entropy_{mean,min,max,std} (cross-worker split entropy)
  worker compute      mean/min/max/std/cv of per-worker epochs-per-second from the
                      machine benchmark, over the participating workers, joined by
                      (node, vmid)

Three columns count workers and mean different things: num_workers is the intended
count from division.json; n_workers is the number of worker lines in workers.txt;
and n_workers_joined counts the master's `new_worker` events, i.e. the workers that
actually registered and were eligible for the aggregation pool.
n_workers_joined < num_workers marks a short-pool run.

local_epochs is 0 for every Centralized row by construction (T46) — a sentinel for
"this algorithm has no local-training concept," not a measured zero. Do not use it as
a multiplicative or log-scale compute term without gating on fl_algo; a consumer that
drops fl_algo (e.g. after a groupby or column subset) cannot recover which zeros are
structural.

Targets (master log_0.jsonl, single clock; T09)
  performance         best validation main metric (mcc↑ clf / smape↓ reg). NB: the
                      regression metric is logged under the key `mape` but is
                      actually SMAPE (FederatedABC.smape); `main_metric` reports
                      that key verbatim.
  constant_mean_smape   regression only: the SMAPE on the dataset's validation
                      split of a constant prediction equal to the training-target
                      mean, from <data-dir>/<dataset>/_data/y_train.npy and
                      y_val.npy in original units. Empty for classification and,
                      with a warning, when the cache or numpy is unavailable.
  beats_constant_mean   regression only: performance < constant_mean_smape.
                      Empty whenever constant_mean_smape is. Rows that do not beat
                      the baseline are kept. Outcome, not a predictor.
  total_time_s        master start→end delta
  comm_bytes_{sent,recv,total}   Σ payload_size of the master's send/recv events
  n_epochs            last epoch reached: the `epoch` field of the final epoch
                      event. An OUTCOME, not a feature; exclude it from the
                      predictor set (leakage) unless modelling it as a target. A
                      run with any epoch event lacking a positive integer `epoch`
                      is dropped with a warning.
  n_validations       number of epoch (validation) events. Equals n_epochs, except
                      for CentralizedSync runs logged before the per-epoch
                      validation fix, which validated every k > 1 epochs when
                      min_workers did not divide the pool's total batches.
  epoch_validation_gap  n_validations != n_epochs: flags those pre-fix
                      CentralizedSync runs, whose n_epochs can overshoot the
                      epoch cap. Outcome, not a predictor.
  compute_time_{total,max}_s, comm_time_{total,max}_s, serial_time_total_s,
  validation_time_s,
  comm_skew_clamped   time decomposition from log_0.jsonl plus
                      worker_N/log_M.jsonl (flexfl.builtins.event_metrics, the
                      pairing Results uses): worker work, message transit and
                      encode/decode seconds, every interval clipped to the master
                      start-to-end window, _total summed over workers, _max the
                      busiest worker. comm_time_* pairs a master and a worker
                      clock; comm_skew_clamped counts pairs whose negative
                      duration was clamped to 0. Empty, with a warning, when a
                      run has no worker logs or no work inside the window.
                      Outcomes, like n_epochs: not predictors.
"""

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_meta_features import (  # noqa: E402
    DEFAULT_METADATA_DIR,
    architecture_features,
    meta_features,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from flexfl.builtins.event_metrics import decomposition  # noqa: E402

DEFAULT_HPO_DIR = (
    Path(__file__).resolve().parent.parent / "results/hyperparameter_optimization"
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DECOMPOSITION_COLUMNS = [
    "compute_time_total_s",
    "compute_time_max_s",
    "comm_time_total_s",
    "comm_time_max_s",
    "serial_time_total_s",
    "validation_time_s",
    "comm_skew_clamped",
]

COLUMNS = [
    "strategy",
    "strategy_iid",
    "strategy_non_iid",
    "strategy_dirichlet",
    "combo",
    "n_atnog_test1",
    "n_hobbit",
    "n_samwise",
    "num_workers",
    "n_workers_joined",
    "dataset",
    "fl_algo",
    "fl_algo_CentralizedSync",
    "fl_algo_CentralizedAsync",
    "fl_algo_DecentralizedSync",
    "fl_algo_DecentralizedAsync",
    "repeat",
    "learning_rate",
    "batch_size",
    "patience",
    "delta",
    "local_epochs",
    "epoch_cap",
    "early_stop_on",
    "min_epochs",
    "task",
    "is_classification",
    "is_categorical",
    "n_samples",
    "n_features",
    "n_classes",
    "total_parameters",
    "n_layers",
    "mean_layer_width",
    "max_layer_width",
    "weight_decay",
    "alpha",
    "distribution_percentage",
    "feat_entropy_mean",
    "feat_entropy_min",
    "feat_entropy_max",
    "feat_entropy_std",
    "n_workers",
    "n_workers_benchmarked",
    "worker_rate_mean",
    "worker_rate_min",
    "worker_rate_max",
    "worker_rate_std",
    "worker_rate_cv",
    "performance",
    "main_metric",
    "constant_mean_smape",
    "beats_constant_mean",
    "total_time_s",
    "comm_bytes_sent",
    "comm_bytes_recv",
    "comm_bytes_total",
    "n_epochs",
    "n_validations",
    "epoch_validation_gap",
    *DECOMPOSITION_COLUMNS,
]

ALGO_ALIASES = {
    "centralizedsync": "CentralizedSync",
    "cs": "CentralizedSync",
    "centralizedasync": "CentralizedAsync",
    "ca": "CentralizedAsync",
    "decentralizedsync": "DecentralizedSync",
    "ds": "DecentralizedSync",
    "decentralizedasync": "DecentralizedAsync",
    "da": "DecentralizedAsync",
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


def read_master_events(rep_dir: Path) -> tuple[Path | None, list[dict], int]:
    logs = sorted(rep_dir.rglob("log_0.jsonl"))
    if not logs:
        return None, [], 0
    events, bad = read_jsonl(logs[0])
    return logs[0], events, bad


EVENT_FIELDS = {
    "start": ("timestamp",),
    "end": ("timestamp",),
    "send": ("sender", "receiver", "payload_size", "timestamp"),
    "recv": ("sender", "receiver", "payload_size", "timestamp"),
    "encode": ("time", "timestamp"),
    "decode": ("time", "timestamp"),
    "working_start": ("timestamp",),
    "working_end": ("timestamp",),
    "failure": ("timestamp",),
    "validation_start": ("timestamp",),
    "validation_end": ("timestamp",),
}
ANOMALY_WARNINGS = (
    ("n_unmatched_comms", "send/recv events unmatched"),
    ("n_orphan_comms", "master send/recv events address an absent worker log"),
    ("n_unclosed_work_logs", "worker logs with unpaired working_start/end"),
    ("n_unmatched_validations", "validation_start/end events unpaired"),
)


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    events, bad = [], 0
    for raw in path.read_bytes().splitlines():
        try:
            line = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            bad += 1
            continue
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            bad += 1
    return events, bad


def well_formed(event: object) -> bool:
    if not isinstance(event, dict) or not isinstance(event.get("event"), str):
        return False
    return all(
        isinstance(event.get(field), (int, float))
        and not isinstance(event.get(field), bool)
        for field in EVENT_FIELDS.get(event["event"], ())
    )


def time_decomposition(
    rep_dir: Path, master_log: Path, events: list[dict], master_bad: int
) -> tuple[dict, str | None, list[str]]:
    empty = dict.fromkeys(DECOMPOSITION_COLUMNS)
    master = [e for e in events if well_formed(e)]
    notes = []
    master_malformed = master_bad + len(events) - len(master)
    if master_malformed:
        notes.append(f"{master_malformed} malformed records skipped in {master_log}")
    logs, log2node = {0: master}, {0: 0}
    for path in sorted(master_log.parent.glob("worker_*/log_*.jsonl")):
        log_match = re.fullmatch(r"log_([0-9]+)\.jsonl", path.name)
        node_match = re.fullmatch(r"worker_([0-9]+)", path.parent.name)
        if log_match is None or node_match is None:
            notes.append(f"unrecognized worker log name, ignored: {path}")
            continue
        log_id, node_id = int(log_match[1]), int(node_match[1])
        if log_id in logs:
            notes.append(f"duplicate worker log id {log_id}, ignored: {path}")
            continue
        try:
            parsed, bad = read_jsonl(path)
        except OSError as e:
            notes.append(f"unreadable worker log ({e}), ignored: {path}")
            continue
        worker_events = [e for e in parsed if well_formed(e)]
        bad += len(parsed) - len(worker_events)
        if bad:
            notes.append(f"{bad} malformed records skipped in {path}")
        logs[log_id] = worker_events
        log2node[log_id] = node_id
    if len(logs) == 1:
        return empty, "no worker logs", notes
    t0 = next(e["timestamp"] for e in events if e.get("event") == "start")
    t1 = [e for e in events if e.get("event") == "end"][-1]["timestamp"]
    split = decomposition(logs, log2node, t0, t1)
    for key, label in ANOMALY_WARNINGS:
        if split[key]:
            notes.append(f"{split[key]} {label} in {rep_dir}")
    if (
        split["n_work_intervals_in_window"] == 0
        and split["n_work_events_in_window"] == 0
    ):
        return empty, "no work inside the master window", notes
    return {k: split[k] for k in DECOMPOSITION_COLUMNS}, None, notes


def compute_targets(events: list[dict], is_classification: bool) -> dict | None:
    starts = [e for e in events if e.get("event") == "start"]
    ends = [e for e in events if e.get("event") == "end"]
    epochs = [e for e in events if e.get("event") == "epoch"]
    if not starts or not ends or not epochs:
        return None
    main = "mcc" if is_classification else "mape"
    vals = [
        v
        for e in epochs
        if isinstance((v := e.get(main)), (int, float)) and math.isfinite(v)
    ]
    if not vals:
        return None
    perf = max(vals) if is_classification else min(vals)
    if not math.isfinite(perf):
        return None
    numbers = [e.get("epoch") for e in epochs]
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in numbers):
        return None
    last_epoch = numbers[-1]
    sent = sum(e.get("payload_size", 0) for e in events if e.get("event") == "send")
    recv = sum(e.get("payload_size", 0) for e in events if e.get("event") == "recv")
    return {
        "performance": perf,
        "main_metric": main,
        "total_time_s": ends[-1]["timestamp"] - starts[0]["timestamp"],
        "comm_bytes_sent": sent,
        "comm_bytes_recv": recv,
        "comm_bytes_total": sent + recv,
        "n_epochs": last_epoch,
        "n_validations": len(epochs),
        "epoch_validation_gap": len(epochs) != last_epoch,
    }


def constant_mean_smape(
    data_dir: Path | None, dataset: str
) -> tuple[float | None, str | None]:
    if data_dir is None:
        return None, "no data dir given"
    cache = data_dir / dataset / "_data"
    paths = [cache / "y_train.npy", cache / "y_val.npy"]
    try:
        missing = [p.name for p in paths if not p.is_file()]
    except OSError as e:
        return None, f"cannot read cache {cache} ({e})"
    if missing:
        return None, f"missing {', '.join(missing)} in {cache}"
    # A module-level numpy or FederatedABC import breaks the stdlib-only import test.
    try:
        import numpy as np

        from flexfl.builtins.FederatedABC import smape
    except Exception as e:
        return None, f"cannot import numpy or flexfl ({type(e).__name__}: {e})"
    arrays = []
    for path in paths:
        try:
            y = np.load(path, allow_pickle=False)
        except Exception as e:
            return None, f"unreadable {path.name} ({type(e).__name__}: {e})"
        if not isinstance(y, np.ndarray):
            y.close()
            return None, f"{path.name} is not a .npy array"
        if (
            not (
                np.issubdtype(y.dtype, np.floating)
                or np.issubdtype(y.dtype, np.integer)
            )
            or y.size == 0
            or y.ndim > 2
            or (y.ndim == 2 and y.shape[1] != 1)
        ):
            return None, f"{path.name} is not a non-empty single real target"
        y = y.astype(np.float64).ravel()
        if not np.all(np.isfinite(y)):
            return None, f"{path.name} has non-finite targets"
        arrays.append(y)
    y_train, y_val = arrays
    with np.errstate(divide="ignore", invalid="ignore"):
        value = float(smape(y_val, np.full(y_val.shape, y_train.mean())))
    if not math.isfinite(value):
        return None, "non-finite baseline"
    return value, None


def worker_compute(workers_txt: Path, benchmark_dir: Path) -> dict:
    empty = {
        "n_workers": None,
        "n_workers_benchmarked": 0,
        "worker_rate_mean": None,
        "worker_rate_min": None,
        "worker_rate_max": None,
        "worker_rate_std": None,
        "worker_rate_cv": None,
    }
    if not workers_txt.exists():
        return empty
    lines = [
        ln.strip()
        for ln in workers_txt.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
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
        model_rates = [
            r
            for m in results.values()
            if isinstance((r := m.get("avg_epochs_per_second")), (int, float))
            and math.isfinite(r)
        ]
        if model_rates:
            rates.append(statistics.fmean(model_rates))
    legacy_key = {"_legacy_workers_txt": str(workers_txt)} if legacy else {}
    if not rates or len(rates) < len(worker_entries):
        return {
            **empty,
            "n_workers": len(worker_entries),
            "n_workers_benchmarked": len(rates),
            **legacy_key,
        }
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
            hp = {
                k: a.get(k)
                for k in (
                    "learning_rate",
                    "batch_size",
                    "patience",
                    "delta",
                    "local_epochs",
                )
                if a.get(k) is not None
            }
    return {
        "learning_rate": hp.get("learning_rate"),
        "batch_size": hp.get("batch_size"),
        "patience": hp.get("patience"),
        "delta": hp.get("delta"),
        "local_epochs": hp.get("local_epochs"),
    }


def recorded_args(
    master_log: Path | None,
) -> tuple[dict | None, str | None, str | None]:
    """The args.json beside the master log, why it is missing, and any read
    error."""
    if master_log is None or not (master_log.parent / "args.json").is_file():
        return None, "no args.json beside the master log", None
    try:
        args = load_json(master_log.parent / "args.json")
    except (OSError, ValueError) as e:
        return None, None, str(e)
    if not isinstance(args, dict):
        return None, "args.json is not a JSON object", None
    return args, None, None


def recorded_epoch_cap(
    args: dict | None, missing_reason: str | None
) -> tuple[object, str | None]:
    """The `epochs` in a run's args.json, or why it is missing."""
    if args is None:
        return None, missing_reason
    if "epochs" not in args:
        return None, "args.json has no epochs"
    return args["epochs"], None


EARLY_STOP_RULES = ("loss", "metric")
LEGACY_EARLY_STOP_RULE = ("metric", 0)


def recorded_early_stop_rule(
    args: dict | None, missing_reason: str | None
) -> tuple[object, object, str | None]:
    """The `early_stop_on` and `min_epochs` in a run's args.json, or why both
    are missing.

    A pair with only one key present is returned with None for the other, so it
    fails validation instead of taking the legacy rule.
    """
    if args is None:
        return None, None, missing_reason
    if "early_stop_on" not in args and "min_epochs" not in args:
        return None, None, "args.json has no early_stop_on/min_epochs"
    return args.get("early_stop_on"), args.get("min_epochs"), None


def assemble(
    results_dir: Path,
    metadata_dir: Path,
    hpo_dir: Path,
    legacy_epoch_cap: int | None = None,
    legacy_early_stop_rule: bool = False,
    *,
    data_dir: Path | None = None,
) -> tuple[list[dict], list[str]]:
    benchmark_dir = results_dir / "benchmark"
    rows, warnings = [], []
    baselines = {}
    for success in sorted(results_dir.rglob("_SUCCESS")):
        rep_dir = success.parent
        rel = rep_dir.relative_to(results_dir).parts
        if len(rel) < 5 or not rel[-1].startswith("rep_"):
            warnings.append(f"unexpected path, skipped: {rep_dir}")
            continue
        strategy, combo, dataset, fl_algo, rep = (
            rel[-5],
            rel[-4],
            rel[-3],
            rel[-2],
            rel[-1],
        )

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
            warnings.append(
                f"missing n_features/n_classes for {dataset}, skipped: {rep_dir}"
            )
            continue

        hpo_file = hpo_dir / f"{dataset}.json"
        if not hpo_file.exists():
            warnings.append(f"no HPO config for {dataset}, skipped: {rep_dir}")
            continue
        try:
            af = architecture_features(
                load_json(hpo_file), mf["n_features"], mf["n_classes"]
            )
        except (KeyError, TypeError, ValueError, statistics.StatisticsError) as e:
            warnings.append(
                f"malformed HPO config for {dataset} ({e}), skipped: {rep_dir}"
            )
            continue

        master_log, events, master_bad = read_master_events(rep_dir)
        targets = compute_targets(events, mf["is_classification"])
        if targets is None:
            warnings.append(
                "targets uncomputable (missing start/end/epoch or epoch number), "
                f"skipped: {rep_dir}"
            )
            continue

        args, missing_args, read_error = recorded_args(master_log)
        if read_error is not None:
            warnings.append(f"unreadable args.json ({read_error}), skipped: {rep_dir}")
            continue

        epoch_cap, missing_reason = recorded_epoch_cap(args, missing_args)
        if missing_reason is not None:
            if legacy_epoch_cap is None:
                warnings.append(
                    f"no recorded epoch cap ({missing_reason}), skipped: {rep_dir}"
                )
                continue
            epoch_cap = legacy_epoch_cap
        if (
            not isinstance(epoch_cap, int)
            or isinstance(epoch_cap, bool)
            or epoch_cap < 1
        ):
            warnings.append(
                f"invalid epoch cap {epoch_cap!r} in args.json, skipped: {rep_dir}"
            )
            continue

        early_stop_on, min_epochs, missing_rule = recorded_early_stop_rule(
            args, missing_args
        )
        if missing_rule is not None:
            if not legacy_early_stop_rule:
                warnings.append(
                    f"no recorded early-stop rule ({missing_rule}), skipped: {rep_dir}"
                )
                continue
            early_stop_on, min_epochs = LEGACY_EARLY_STOP_RULE
        if (
            early_stop_on not in EARLY_STOP_RULES
            or not isinstance(min_epochs, int)
            or isinstance(min_epochs, bool)
            or min_epochs < 0
        ):
            warnings.append(
                f"invalid early-stop rule ({early_stop_on!r}, {min_epochs!r}) "
                f"in args.json, skipped: {rep_dir}"
            )
            continue

        decomposition_columns, null_cause, decomposition_notes = time_decomposition(
            rep_dir, master_log, events, master_bad
        )
        warnings.extend(decomposition_notes)
        if null_cause is not None:
            warnings.append(f"time decomposition unavailable ({null_cause}): {rep_dir}")

        row = {
            "strategy": division.get("strategy", strategy),
            "combo": combo,
            **parse_combo(combo),
            "num_workers": division.get("num_workers"),
            "n_workers_joined": sum(
                1 for e in events if e.get("event") == "new_worker"
            ),
            "dataset": dataset,
            "fl_algo": fl_algo,
            "repeat": int(rep.split("_")[1]),
            **fl_hyperparameters(rep_dir),
            "epoch_cap": epoch_cap,
            "early_stop_on": early_stop_on,
            "min_epochs": min_epochs,
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
            **worker_compute(
                rep_dir.parent.parent.parent / "workers.txt", benchmark_dir
            ),
            **targets,
            **decomposition_columns,
            "_decomposition_null_cause": null_cause,
        }
        canonical_fl_algo = ALGO_ALIASES.get(row["fl_algo"].lower())
        if canonical_fl_algo is None:
            warnings.append(
                f"unrecognized fl_algo {row['fl_algo']!r}, skipped: {rep_dir}"
            )
            continue
        if canonical_fl_algo in CENTRALIZED_ALGOS and row["local_epochs"] is None:
            row["local_epochs"] = 0
        elif row["local_epochs"] is None:
            warnings.append(
                f"local_epochs unrecorded for {rep_dir} (fl_algo={row['fl_algo']})"
            )
        if all(
            row[k] is None for k in ("learning_rate", "batch_size", "patience", "delta")
        ):
            warnings.append(f"no FL hyperparameters recorded for {rep_dir}")
        for algo in (
            "CentralizedSync",
            "CentralizedAsync",
            "DecentralizedSync",
            "DecentralizedAsync",
        ):
            row[f"fl_algo_{algo}"] = int(canonical_fl_algo == algo)
        for strat in ("iid", "non_iid", "dirichlet"):
            row[f"strategy_{strat}"] = int(row["strategy"] == strat)
        if sum(row[f"strategy_{s}"] for s in ("iid", "non_iid", "dirichlet")) != 1:
            warnings.append(
                f"unrecognized strategy {row['strategy']!r}, skipped: {rep_dir}"
            )
            continue
        legacy_workers_txt = row.get("_legacy_workers_txt")
        if legacy_workers_txt is not None:
            warnings.append(
                "legacy IP-only workers.txt, worker compute skipped: "
                f"{legacy_workers_txt}"
            )
        if (
            row.get("n_workers")
            and row.get("n_workers_benchmarked", 0) < row["n_workers"]
        ):
            warnings.append(
                f"worker compute features incomplete for {rep_dir}: "
                f"{row['n_workers_benchmarked']}/{row['n_workers']} "
                "workers benchmarked "
                f"(missing machine_benchmark_<node>_<vmid>.json for some workers)"
            )
        row["constant_mean_smape"] = row["beats_constant_mean"] = None
        if not mf["is_classification"]:
            if dataset not in baselines:
                baselines[dataset], reason = constant_mean_smape(data_dir, dataset)
                if reason is not None:
                    warnings.append(
                        f"constant-mean baseline unavailable for {dataset} "
                        f"({reason}), its baseline columns are empty"
                    )
            baseline = baselines[dataset]
            if baseline is not None:
                row["constant_mean_smape"] = baseline
                row["beats_constant_mean"] = row["performance"] < baseline
        rows.append(row)
    return rows, warnings


def main():
    p = argparse.ArgumentParser(
        description="Assemble the per-run meta-learning table (T11)."
    )
    p.add_argument("--results-dir", type=Path, default=Path("results"))
    p.add_argument("--metadata-dir", type=Path, default=DEFAULT_METADATA_DIR)
    p.add_argument("--hpo-dir", type=Path, default=DEFAULT_HPO_DIR)
    p.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="preprocessed dataset caches for the regression constant-mean baseline",
    )
    p.add_argument("--out", type=Path, default=Path("results/meta_dataset.csv"))
    p.add_argument(
        "--legacy-epoch-cap",
        type=int,
        default=None,
        help="epoch cap to assign to runs that recorded none (default: drop them)",
    )
    p.add_argument(
        "--legacy-early-stop-rule",
        action="store_true",
        help="assign early_stop_on=metric, min_epochs=0 to runs that recorded no "
        "early-stop rule (default: drop them)",
    )
    args = p.parse_args()
    if args.legacy_epoch_cap is not None and args.legacy_epoch_cap < 1:
        p.error("--legacy-epoch-cap must be a positive integer")

    rows, warnings = assemble(
        args.results_dir,
        args.metadata_dir,
        args.hpo_dir,
        args.legacy_epoch_cap,
        args.legacy_early_stop_rule,
        data_dir=args.data_dir,
    )
    for w in warnings:
        print(f"  ! {w}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.out} ({len(warnings)} skipped).")
    null_causes = Counter(
        r["_decomposition_null_cause"] for r in rows if r["_decomposition_null_cause"]
    )
    if null_causes:
        detail = ", ".join(
            f"{cause}: {count}" for cause, count in sorted(null_causes.items())
        )
        print(
            "Time decomposition unavailable for "
            f"{sum(null_causes.values())} of {len(rows)} rows ({detail})."
        )


if __name__ == "__main__":
    main()
