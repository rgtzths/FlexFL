import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
from assemble_meta_dataset import (
    COLUMNS,
    DECOMPOSITION_COLUMNS,
    assemble,
    compute_targets,
    constant_mean_smape,
    parse_combo,
    worker_compute,
)
from run_logs import MASTER_EVENTS, write_run_logs

GOLDEN = [6.5, 4.5, 2.0, 1.25, 1.0, 1.0, 1]


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_jsonl(path: Path, events: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


# --- parse_combo ---


def test_parse_combo_valid():
    result = parse_combo("atnog-test1_2_hobbit_4_samwise_8")
    assert (result["n_atnog_test1"], result["n_hobbit"], result["n_samwise"]) == (
        2,
        4,
        8,
    )


def test_parse_combo_missing_node_token():
    result = parse_combo("atnog-test1_2_hobbit_4")
    assert result["n_samwise"] is None


# --- compute_targets ---


def test_compute_targets_classification_takes_max_mcc():
    events = [
        {"event": "start", "timestamp": 1000},
        {"event": "epoch", "epoch": 1, "mcc": 0.5},
        {"event": "epoch", "epoch": 2, "mcc": 0.8},
        {"event": "send", "payload_size": 100},
        {"event": "recv", "payload_size": 50},
        {"event": "end", "timestamp": 1010},
    ]
    result = compute_targets(events, is_classification=True)
    assert result["performance"] == 0.8
    assert result["main_metric"] == "mcc"
    assert result["total_time_s"] == 10
    assert result["comm_bytes_sent"] == 100
    assert result["comm_bytes_recv"] == 50
    assert result["comm_bytes_total"] == 150


def test_compute_targets_regression_takes_min_mape():
    events = [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "epoch": 1, "mape": 0.3},
        {"event": "epoch", "epoch": 2, "mape": 0.1},
        {"event": "end", "timestamp": 5},
    ]
    result = compute_targets(events, is_classification=False)
    assert result["performance"] == 0.1
    assert result["main_metric"] == "mape"


def test_compute_targets_none_when_missing_start_or_end_or_epoch():
    assert (
        compute_targets([{"event": "start", "timestamp": 0}], is_classification=True)
        is None
    )
    assert (
        compute_targets([{"event": "end", "timestamp": 0}], is_classification=True)
        is None
    )
    assert (
        compute_targets(
            [{"event": "start", "timestamp": 0}, {"event": "end", "timestamp": 1}],
            is_classification=True,
        )
        is None
    )


def test_compute_targets_none_when_no_epoch_has_numeric_main_metric():
    events = [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "mcc": None},
        {"event": "end", "timestamp": 1},
    ]
    assert compute_targets(events, is_classification=True) is None


def test_compute_targets_n_epochs_is_last_logged_epoch_not_validation_count():
    events = [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "epoch": 14, "mcc": 0.5},
        {"event": "epoch", "epoch": 28, "mcc": 0.6},
        {"event": "epoch", "epoch": 42, "mcc": 0.7},
        {"event": "end", "timestamp": 5},
    ]
    result = compute_targets(events, is_classification=True)
    assert (
        result["n_epochs"],
        result["n_validations"],
        result["epoch_validation_gap"],
    ) == (42, 3, True)


def test_compute_targets_no_validation_gap_when_every_epoch_validated():
    events = [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "epoch": 1, "mcc": 0.5},
        {"event": "epoch", "epoch": 2, "mcc": 0.6},
        {"event": "end", "timestamp": 5},
    ]
    result = compute_targets(events, is_classification=True)
    assert (
        result["n_epochs"],
        result["n_validations"],
        result["epoch_validation_gap"],
    ) == (2, 2, False)


@pytest.mark.parametrize(
    "last_epoch",
    (
        {},
        {"epoch": None},
        {"epoch": True},
        {"epoch": 0},
        {"epoch": 2.0},
        {"epoch": "2"},
    ),
)
def test_compute_targets_none_when_last_epoch_number_invalid(last_epoch):
    events = [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "epoch": 1, "mcc": 0.5},
        {"event": "epoch", "mcc": 0.6, **last_epoch},
        {"event": "end", "timestamp": 5},
    ]
    assert compute_targets(events, is_classification=True) is None


@pytest.mark.parametrize(
    "first_epoch",
    (
        {},
        {"epoch": None},
        {"epoch": True},
        {"epoch": 0},
        {"epoch": 1.0},
        {"epoch": "1"},
    ),
)
def test_compute_targets_none_when_earlier_epoch_number_invalid(first_epoch):
    events = [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "mcc": 0.5, **first_epoch},
        {"event": "epoch", "epoch": 2, "mcc": 0.6},
        {"event": "end", "timestamp": 5},
    ]
    assert compute_targets(events, is_classification=True) is None


# --- worker_compute ---


def make_benchmark_file(benchmark_dir: Path, node: str, vmid: str, rate: float):
    write_json(
        benchmark_dir / f"machine_benchmark_{node}_{vmid}.json",
        {"results": {"model_a": {"avg_epochs_per_second": rate}}},
    )


def test_worker_compute_joins_by_node_and_vmid(tmp_path):
    benchmark_dir = tmp_path / "benchmark"
    make_benchmark_file(benchmark_dir, "hobbit", "108", 2.0)
    make_benchmark_file(benchmark_dir, "samwise", "106", 4.0)
    workers_txt = tmp_path / "workers.txt"
    workers_txt.write_text(
        "10.0.0.1 frodo 104\n" "10.0.0.2 hobbit 108\n" "10.0.0.3 samwise 106\n"
    )

    result = worker_compute(workers_txt, benchmark_dir)

    assert result["n_workers"] == 2
    assert result["n_workers_benchmarked"] == 2
    assert result["worker_rate_mean"] == 3.0
    assert result["worker_rate_min"] == 2.0
    assert result["worker_rate_max"] == 4.0


def test_worker_compute_anchor_excluded_from_n_workers(tmp_path):
    benchmark_dir = tmp_path / "benchmark"
    make_benchmark_file(benchmark_dir, "hobbit", "108", 2.0)
    workers_txt = tmp_path / "workers.txt"
    workers_txt.write_text("10.0.0.1 frodo 104\n10.0.0.2 hobbit 108\n")

    result = worker_compute(workers_txt, benchmark_dir)

    assert result["n_workers"] == 1


def test_worker_compute_missing_benchmark_file_partial_set_nulls_aggregate(tmp_path):
    benchmark_dir = tmp_path / "benchmark"
    make_benchmark_file(benchmark_dir, "hobbit", "108", 2.0)
    workers_txt = tmp_path / "workers.txt"
    workers_txt.write_text(
        "10.0.0.1 frodo 104\n" "10.0.0.2 hobbit 108\n" "10.0.0.3 samwise 999\n"
    )

    result = worker_compute(workers_txt, benchmark_dir)

    assert result["n_workers"] == 2
    assert result["n_workers_benchmarked"] == 1
    assert result["worker_rate_mean"] is None


def test_worker_compute_full_benchmark_set_populates_aggregate(tmp_path):
    benchmark_dir = tmp_path / "benchmark"
    make_benchmark_file(benchmark_dir, "hobbit", "108", 2.0)
    make_benchmark_file(benchmark_dir, "samwise", "999", 4.0)
    workers_txt = tmp_path / "workers.txt"
    workers_txt.write_text(
        "10.0.0.1 frodo 104\n" "10.0.0.2 hobbit 108\n" "10.0.0.3 samwise 999\n"
    )

    result = worker_compute(workers_txt, benchmark_dir)

    assert result["n_workers"] == 2
    assert result["n_workers_benchmarked"] == 2
    assert result["worker_rate_mean"] == 3.0


def test_worker_compute_different_nodes_sharing_vmid_resolve_to_different_files(
    tmp_path,
):
    benchmark_dir = tmp_path / "benchmark"
    make_benchmark_file(benchmark_dir, "hobbit", "100", 2.0)
    make_benchmark_file(benchmark_dir, "atnog-test1", "100", 6.0)
    workers_txt = tmp_path / "workers.txt"
    workers_txt.write_text(
        "10.0.0.1 frodo 104\n" "10.0.0.2 hobbit 100\n" "10.0.0.3 atnog-test1 100\n"
    )

    result = worker_compute(workers_txt, benchmark_dir)

    assert result["n_workers_benchmarked"] == 2
    assert result["worker_rate_min"] == 2.0
    assert result["worker_rate_max"] == 6.0


def test_worker_compute_workers_sharing_ip_resolve_to_own_files(tmp_path):
    benchmark_dir = tmp_path / "benchmark"
    make_benchmark_file(benchmark_dir, "hobbit", "108", 2.0)
    make_benchmark_file(benchmark_dir, "samwise", "106", 4.0)
    workers_txt = tmp_path / "workers.txt"
    workers_txt.write_text(
        "10.0.0.1 frodo 104\n" "10.0.0.9 hobbit 108\n" "10.0.0.9 samwise 106\n"
    )

    result = worker_compute(workers_txt, benchmark_dir)

    assert result["n_workers"] == 2
    assert result["n_workers_benchmarked"] == 2
    assert result["worker_rate_min"] == 2.0
    assert result["worker_rate_max"] == 4.0


def test_worker_compute_legacy_ip_only_format_sets_legacy_sentinel_key(tmp_path):
    benchmark_dir = tmp_path / "benchmark"
    workers_txt = tmp_path / "workers.txt"
    workers_txt.write_text("10.0.0.1\n10.0.0.2\n")

    result = worker_compute(workers_txt, benchmark_dir)

    assert result["_legacy_workers_txt"] == str(workers_txt)
    assert result["worker_rate_mean"] is None


def test_worker_compute_missing_workers_txt_returns_empty(tmp_path):
    result = worker_compute(tmp_path / "does_not_exist.txt", tmp_path / "benchmark")

    assert result["n_workers"] is None
    assert result["worker_rate_mean"] is None


# --- assemble end-to-end ---


def build_synthetic_run(
    results_dir: Path,
    metadata_dir: Path,
    hpo_dir: Path,
    *,
    strategy="iid",
    combo="atnog-test1_0_hobbit_1_samwise_0",
    dataset="ds_a",
    fl_algo="CentralizedSync",
    rep=1,
    sentinel="_SUCCESS",
    with_epochs=True,
    workers_txt=None,
    with_hpo=True,
    hyperparameters=None,
    new_workers=0,
    epoch_cap=200,
    early_stop_rule=("loss", 10),
):
    rep_dir = results_dir / strategy / combo / dataset / fl_algo / f"rep_{rep}"
    rep_dir.mkdir(parents=True, exist_ok=True)

    events = [
        {"event": "new_worker", "node_id": i, "info": {}}
        for i in range(1, new_workers + 1)
    ]
    events.append({"event": "start", "timestamp": 0})
    if with_epochs:
        events.append({"event": "epoch", "epoch": 1, "mcc": 0.7})
    events.append({"event": "end", "timestamp": 5})
    write_jsonl(rep_dir / "log_0.jsonl", events)
    if epoch_cap is not None:
        args = {"epochs": epoch_cap}
        if early_stop_rule is not None:
            args["early_stop_on"], args["min_epochs"] = early_stop_rule
        write_json(rep_dir / "args.json", args)

    (rep_dir / sentinel).write_text("")

    if workers_txt is not None:
        (rep_dir.parent.parent.parent / "workers.txt").write_text(workers_txt)

    write_json(
        metadata_dir / f"{dataset}.json",
        {
            "type": "classification",
            "input_shape": [4],
            "samples": 100,
            "output_size": 2,
        },
    )
    if with_hpo:
        write_json(
            hpo_dir / f"{dataset}.json",
            {
                "n_layers": 2,
                "n_units_l0": 8,
                "n_units_l1": 4,
                "weight_decay": 0.001,
            },
        )
    if hyperparameters is not None:
        write_json(rep_dir / "hyperparameters.json", hyperparameters)
    return rep_dir


def build_timed_run(
    results_dir: Path, metadata_dir: Path, hpo_dir: Path, **kwargs
) -> Path:
    rep_dir = build_synthetic_run(results_dir, metadata_dir, hpo_dir, **kwargs)
    (rep_dir / "log_0.jsonl").unlink()
    master = [
        *MASTER_EVENTS[:-1],
        {"event": "epoch", "epoch": 1, "mcc": 0.7, "timestamp": 105.0},
        MASTER_EVENTS[-1],
    ]
    folder = write_run_logs(rep_dir / "2026-01-01_00:00:00", master)
    args_file = rep_dir / "args.json"
    if args_file.exists():
        args_file.replace(folder / "args.json")
    return folder


def test_assemble_one_row_per_success(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir)

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    assert rows[0]["dataset"] == "ds_a"


def test_assemble_excludes_failed(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, sentinel="_FAILED")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows == []


def test_assemble_too_shallow_path_warns_and_skipped(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    shallow = results_dir / "onlyonelevel"
    shallow.mkdir(parents=True)
    (shallow / "_SUCCESS").write_text("")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows == []
    assert any("unexpected path" in w for w in warnings)


def test_assemble_no_epochs_dropped_no_nan_reaches_row(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, with_epochs=False)

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows == []
    assert any("targets uncomputable" in w for w in warnings)


def test_assemble_legacy_ip_only_workers_txt_warns(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir, metadata_dir, hpo_dir, workers_txt="10.0.0.1\n10.0.0.2\n"
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    assert any(
        "legacy IP-only workers.txt, worker compute skipped" in w for w in warnings
    )


def test_assemble_incomplete_worker_benchmark_warns(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    make_benchmark_file(results_dir / "benchmark", "hobbit", "108", 2.0)
    build_synthetic_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        workers_txt=(
            "10.0.0.1 frodo 104\n" "10.0.0.2 hobbit 108\n" "10.0.0.3 samwise 999\n"
        ),
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    assert any(
        "worker compute features incomplete" in w and "1/2 workers benchmarked" in w
        for w in warnings
    )


def test_assemble_nan_metric_dropped_no_nan_reaches_csv(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    rep_dir = (
        results_dir
        / "iid"
        / "atnog-test1_0_hobbit_1_samwise_0"
        / "ds_a"
        / "fedavg"
        / "rep_1"
    )
    rep_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        rep_dir / "log_0.jsonl",
        [
            {"event": "start", "timestamp": 0},
            {"event": "epoch", "mcc": float("nan")},
            {"event": "end", "timestamp": 5},
        ],
    )
    (rep_dir / "_SUCCESS").write_text("")
    write_json(
        metadata_dir / "ds_a.json",
        {
            "type": "classification",
            "input_shape": [4],
            "samples": 100,
            "output_size": 2,
        },
    )
    write_json(
        hpo_dir / "ds_a.json",
        {
            "n_layers": 2,
            "n_units_l0": 8,
            "n_units_l1": 4,
            "weight_decay": 0.001,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows == []
    assert any("targets uncomputable" in w for w in warnings)

    out_csv = tmp_path / "meta_dataset.csv"
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            script,
            "--results-dir",
            str(results_dir),
            "--metadata-dir",
            str(metadata_dir),
            "--hpo-dir",
            str(hpo_dir),
            "--out",
            str(out_csv),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    with open(out_csv, newline="") as f:
        lines = list(csv.reader(f))
    assert len(lines) == 1  # header only, no data row for the NaN run
    assert "targets uncomputable" in result.stderr
    assert "no HPO config" not in result.stderr


def run_assemble_cli(
    script: str, results_dir: Path, metadata_dir: Path, hpo_dir: Path, out_csv: Path
):
    return subprocess.run(
        [
            sys.executable,
            script,
            "--results-dir",
            str(results_dir),
            "--metadata-dir",
            str(metadata_dir),
            "--hpo-dir",
            str(hpo_dir),
            "--out",
            str(out_csv),
        ],
        capture_output=True,
        text=True,
    )


def test_assemble_idempotent_byte_identical_over_growing_tree(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_a")
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )

    out_a1 = tmp_path / "out_a1.csv"
    result_a1 = run_assemble_cli(script, results_dir, metadata_dir, hpo_dir, out_a1)
    assert result_a1.returncode == 0

    out_a2 = tmp_path / "out_a2.csv"
    result_a2 = run_assemble_cli(script, results_dir, metadata_dir, hpo_dir, out_a2)
    assert result_a2.returncode == 0

    assert out_a1.read_bytes() == out_a2.read_bytes()

    a1_lines = out_a1.read_text().splitlines()
    run_a_line = next(ln for ln in a1_lines if "ds_a" in ln)

    build_synthetic_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        dataset="ds_b",
        combo="atnog-test1_1_hobbit_0_samwise_0",
    )
    out_b = tmp_path / "out_b.csv"
    result_b = run_assemble_cli(script, results_dir, metadata_dir, hpo_dir, out_b)
    assert result_b.returncode == 0

    b_lines = out_b.read_text().splitlines()
    run_a_line_in_b = next(ln for ln in b_lines if "ds_a" in ln)
    assert run_a_line_in_b == run_a_line
    assert any("ds_b" in ln for ln in b_lines)


def test_assemble_cli_writes_header_exactly_columns(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir)
    out_csv = tmp_path / "meta_dataset.csv"

    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            script,
            "--results-dir",
            str(results_dir),
            "--metadata-dir",
            str(metadata_dir),
            "--hpo-dir",
            str(hpo_dir),
            "--out",
            str(out_csv),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    with open(out_csv, newline="") as f:
        lines = list(csv.reader(f))
    assert lines[0] == COLUMNS
    assert len(lines) == 2  # header + 1 data row


def test_assemble_cli_writes_n_epochs_and_n_validations(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    rep_dir = build_synthetic_run(results_dir, metadata_dir, hpo_dir)
    write_jsonl(
        rep_dir / "log_0.jsonl",
        [
            {"event": "start", "timestamp": 0},
            {"event": "epoch", "epoch": 14, "mcc": 0.6},
            {"event": "epoch", "epoch": 28, "mcc": 0.7},
            {"event": "end", "timestamp": 5},
        ],
    )
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    out_csv = tmp_path / "meta_dataset.csv"
    result = run_assemble_cli(script, results_dir, metadata_dir, hpo_dir, out_csv)
    assert result.returncode == 0, result.stderr
    with open(out_csv, newline="") as f:
        row = next(csv.DictReader(f))
    assert (row["n_epochs"], row["n_validations"], row["epoch_validation_gap"]) == (
        "28",
        "2",
        "True",
    )


def test_assemble_drops_run_whose_last_epoch_has_no_number(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    rep_dir = build_synthetic_run(results_dir, metadata_dir, hpo_dir)
    write_jsonl(
        rep_dir / "log_0.jsonl",
        [
            {"event": "start", "timestamp": 0},
            {"event": "epoch", "mcc": 0.7},
            {"event": "end", "timestamp": 5},
        ],
    )
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert rows == []
    assert any(
        "targets uncomputable (missing start/end/epoch or epoch number)" in w
        for w in warnings
    )


def test_assemble_populates_architecture_columns(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_a")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["total_parameters"] == 86
    assert rows[0]["n_layers"] == 2
    assert rows[0]["mean_layer_width"] == 6.0
    assert rows[0]["max_layer_width"] == 8
    assert rows[0]["weight_decay"] == 0.001


def test_assemble_no_hpo_config_warns_and_skipped(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, with_hpo=False)

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows == []
    assert any("no HPO config for" in w for w in warnings)


def build_run_with_metadata_and_hpo(
    results_dir: Path,
    metadata_dir: Path,
    hpo_dir: Path,
    dataset: str,
    metadata: dict,
    hpo: dict,
    combo="atnog-test1_0_hobbit_1_samwise_0",
    fl_algo="fedavg",
    rep=1,
):
    rep_dir = results_dir / "iid" / combo / dataset / fl_algo / f"rep_{rep}"
    rep_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        rep_dir / "log_0.jsonl",
        [
            {"event": "start", "timestamp": 0},
            {"event": "epoch", "mcc": 0.7},
            {"event": "end", "timestamp": 5},
        ],
    )
    (rep_dir / "_SUCCESS").write_text("")
    write_json(metadata_dir / f"{dataset}.json", metadata)
    write_json(hpo_dir / f"{dataset}.json", hpo)
    return rep_dir


def test_assemble_none_n_features_or_n_classes_warns_and_skipped(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_good")
    build_run_with_metadata_and_hpo(
        results_dir,
        metadata_dir,
        hpo_dir,
        "ds_bad",
        {
            "type": "classification",
            "samples": 100,
            "output_size": 2,
        },  # no input_shape -> n_features None
        {"n_layers": 2, "n_units_l0": 8, "n_units_l1": 4, "weight_decay": 0.001},
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    assert rows[0]["dataset"] == "ds_good"
    assert any("missing n_features/n_classes for ds_bad" in w for w in warnings)


def test_assemble_malformed_hpo_config_warns_and_skipped(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_good")
    build_run_with_metadata_and_hpo(
        results_dir,
        metadata_dir,
        hpo_dir,
        "ds_bad",
        {
            "type": "classification",
            "input_shape": [4],
            "samples": 100,
            "output_size": 2,
        },
        {"n_layers": 2, "n_units_l0": 8, "n_units_l1": 4},  # missing weight_decay
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    assert rows[0]["dataset"] == "ds_good"
    assert any("malformed HPO config for ds_bad" in w for w in warnings)


def test_assemble_empty_units_hpo_config_warns_and_skipped(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_good")
    build_run_with_metadata_and_hpo(
        results_dir,
        metadata_dir,
        hpo_dir,
        "ds_bad",
        {
            "type": "classification",
            "input_shape": [4],
            "samples": 100,
            "output_size": 2,
        },
        {"n_layers": 0, "weight_decay": 0.001},
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    assert rows[0]["dataset"] == "ds_good"
    assert any("malformed HPO config for ds_bad" in w for w in warnings)


def test_assemble_mixed_hpo_coverage_populates_and_skips_selectively(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_with_hpo")
    build_synthetic_run(
        results_dir, metadata_dir, hpo_dir, dataset="ds_without_hpo", with_hpo=False
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    row = rows[0]
    assert row["dataset"] == "ds_with_hpo"
    for col in (
        "total_parameters",
        "n_layers",
        "mean_layer_width",
        "max_layer_width",
        "weight_decay",
    ):
        assert row[col] is not None
    assert any("no HPO config for ds_without_hpo" in w for w in warnings)


def test_assemble_cli_no_hpo_config_skip_does_not_crash(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir, metadata_dir, hpo_dir, dataset="ds_no_hpo", with_hpo=False
    )

    out_csv = tmp_path / "meta_dataset.csv"
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            script,
            "--results-dir",
            str(results_dir),
            "--metadata-dir",
            str(metadata_dir),
            "--hpo-dir",
            str(hpo_dir),
            "--out",
            str(out_csv),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "no HPO config for" in result.stderr
    with open(out_csv, newline="") as f:
        lines = list(csv.reader(f))
    assert len(lines) == 1  # header only, the sole dataset's row was skipped


def test_assemble_cli_writes_local_epochs_zero_for_centralized(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        fl_algo="CentralizedSync",
        hyperparameters={
            "learning_rate": 0.001,
            "batch_size": 256,
            "patience": 5,
            "delta": 0.01,
        },
    )
    out_csv = tmp_path / "meta_dataset.csv"
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    result = run_assemble_cli(script, results_dir, metadata_dir, hpo_dir, out_csv)

    assert result.returncode == 0
    with open(out_csv, newline="") as f:
        row = next(csv.DictReader(f))
    assert row["local_epochs"] == "0"


@pytest.mark.parametrize("fl_algo", ("CentralizedSync", "CentralizedAsync"))
def test_assemble_local_epochs_defaults_to_zero_for_centralized(tmp_path, fl_algo):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        fl_algo=fl_algo,
        hyperparameters={
            "learning_rate": 0.001,
            "batch_size": 256,
            "patience": 5,
            "delta": 0.01,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    row = rows[0]
    assert (
        row["learning_rate"],
        row["batch_size"],
        row["patience"],
        row["delta"],
        row["local_epochs"],
    ) == (0.001, 256, 5, 0.01, 0)


def test_assemble_local_epochs_preserves_sampled_value_for_decentralized(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        fl_algo="DecentralizedSync",
        hyperparameters={
            "learning_rate": 0.001,
            "batch_size": 256,
            "patience": 5,
            "delta": 0.01,
            "local_epochs": 7,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] == 7


def test_assemble_local_epochs_stays_null_when_genuinely_missing_for_decentralized(
    tmp_path,
):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, fl_algo="DecentralizedSync")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] is None
    assert any("local_epochs unrecorded" in w for w in warnings)


def test_assemble_local_epochs_zero_and_warns_without_hyperparameters_centralized(
    tmp_path,
):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, fl_algo="CentralizedSync")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] == 0
    assert any("no FL hyperparameters recorded" in w for w in warnings)


@pytest.mark.parametrize("fl_algo", ("cs", "ca"))
def test_assemble_local_epochs_zero_for_centralized_alias_directory_names(
    tmp_path, fl_algo
):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        fl_algo=fl_algo,
        hyperparameters={
            "learning_rate": 0.001,
            "batch_size": 256,
            "patience": 5,
            "delta": 0.01,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] == 0


@pytest.mark.parametrize("fl_algo", ("CENTRALIZEDSYNC", "Cs"))
def test_assemble_local_epochs_zero_for_centralized_mixed_case_directory_names(
    tmp_path, fl_algo
):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        fl_algo=fl_algo,
        hyperparameters={
            "learning_rate": 0.001,
            "batch_size": 256,
            "patience": 5,
            "delta": 0.01,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] == 0


FL_ALGOS = (
    "CentralizedSync",
    "CentralizedAsync",
    "DecentralizedSync",
    "DecentralizedAsync",
)
STRATEGIES = ("iid", "non_iid", "dirichlet")


@pytest.mark.parametrize("fl_algo", FL_ALGOS)
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_assemble_onehot_fl_algo_and_strategy(tmp_path, strategy, fl_algo):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir, metadata_dir, hpo_dir, strategy=strategy, fl_algo=fl_algo
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    row = rows[0]
    assert sum(row[f"fl_algo_{a}"] for a in FL_ALGOS) == 1
    assert row[f"fl_algo_{fl_algo}"] == 1
    assert sum(row[f"strategy_{s}"] for s in STRATEGIES) == 1
    assert row[f"strategy_{strategy}"] == 1


def test_assemble_unrecognized_fl_algo_warns_and_skips(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, fl_algo="fedavg")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows == []
    assert any("unrecognized fl_algo" in w and "fedavg" in w for w in warnings)


def test_assemble_unrecognized_strategy_warns_and_skips(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, strategy="extreme_non_iid")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows == []
    assert any(
        "unrecognized strategy" in w and "extreme_non_iid" in w for w in warnings
    )


@pytest.mark.parametrize(
    "fl_algo,canonical",
    (
        ("cs", "CentralizedSync"),
        ("ca", "CentralizedAsync"),
        ("ds", "DecentralizedSync"),
        ("da", "DecentralizedAsync"),
        ("CENTRALIZEDSYNC", "CentralizedSync"),
        ("Cs", "CentralizedSync"),
    ),
)
def test_assemble_onehot_resolves_fl_algo_aliases_and_case_variants(
    tmp_path, fl_algo, canonical
):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, fl_algo=fl_algo)

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    row = rows[0]
    assert sum(row[f"fl_algo_{a}"] for a in FL_ALGOS) == 1
    assert row[f"fl_algo_{canonical}"] == 1


def test_assemble_n_workers_joined_matches_num_workers_on_healthy_run(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    rep_dir = build_synthetic_run(results_dir, metadata_dir, hpo_dir, new_workers=4)
    write_json(
        rep_dir.parent.parent / "division.json", {"strategy": "iid", "num_workers": 4}
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["n_workers_joined"] == 4
    assert rows[0]["n_workers_joined"] == rows[0]["num_workers"]


def test_assemble_n_workers_joined_below_num_workers_on_short_pool(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    rep_dir = build_synthetic_run(results_dir, metadata_dir, hpo_dir, new_workers=3)
    write_json(
        rep_dir.parent.parent / "division.json", {"strategy": "iid", "num_workers": 4}
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["n_workers_joined"] == 3
    assert rows[0]["n_workers_joined"] < rows[0]["num_workers"]


def test_assemble_n_workers_joined_is_zero_when_no_worker_registered(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, new_workers=0)

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["n_workers_joined"] == 0


def test_assemble_time_decomposition_clips_to_master_window(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    build_timed_run(results_dir, metadata_dir, hpo_dir)
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert rows[0]["total_time_s"] == 10.0


def test_assemble_time_decomposition_empty_without_worker_logs(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    build_synthetic_run(results_dir, metadata_dir, hpo_dir)
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert len(rows) == 1
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == [None] * 7
    assert any("time decomposition unavailable (no worker logs)" in w for w in warnings)


def test_assemble_time_decomposition_empty_when_no_work_in_window(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    late_work = (
        '{"event": "working_start", "timestamp": 111.0}\n'
        '{"event": "working_end", "timestamp": 113.0}\n'
    )
    for path in (
        run / "worker_1/log_1.jsonl",
        run / "worker_2/log_3.jsonl",
        run / "worker_2/log_4.jsonl",
    ):
        path.write_text(late_work)
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == [None] * 7
    assert any("(no work inside the master window)" in w for w in warnings)
    assert any("6 send/recv events unmatched" in w for w in warnings)


def test_assemble_time_decomposition_skips_malformed_worker_records(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    path = run / "worker_1/log_1.jsonl"
    path.write_text(path.read_text() + '{not json\n{"timestamp": 101}\n')
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any("2 malformed records skipped" in w for w in warnings)


def test_assemble_time_decomposition_counts_malformed_master_records(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    master = run / "log_0.jsonl"
    master.write_text(master.read_text() + "{not json\n")
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(w == f"1 malformed records skipped in {master}" for w in warnings)


def test_assemble_time_decomposition_ignores_non_numeric_log_name(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    stray = run / "worker_1/log_backup.jsonl"
    stray.write_text('{"event": "working_start", "timestamp": 101.0}\n')
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(w == f"unrecognized worker log name, ignored: {stray}" for w in warnings)


def test_assemble_time_decomposition_ignores_non_numeric_worker_folder(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    stray = run / "worker_backup/log_9.jsonl"
    stray.parent.mkdir()
    stray.write_text('{"event": "working_start", "timestamp": 101.0}\n')
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(w == f"unrecognized worker log name, ignored: {stray}" for w in warnings)


def test_assemble_time_decomposition_ignores_unreadable_worker_log(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    stray = run / "worker_1/log_9.jsonl"
    stray.mkdir()
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(
        w.startswith("unreadable worker log (") and w.endswith(f"), ignored: {stray}")
        for w in warnings
    )


def test_assemble_time_decomposition_counts_master_records_in_one_note(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    master = run / "log_0.jsonl"
    master.write_text(master.read_text() + '{not json\n{"event": "send"}\n')
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert [
        w for w in warnings if w.endswith(f"malformed records skipped in {master}")
    ] == [f"2 malformed records skipped in {master}"]


def test_assemble_time_decomposition_counts_non_object_master_lines(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    master = run / "log_0.jsonl"
    master.write_text(master.read_text() + "null\n")
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(w == f"1 malformed records skipped in {master}" for w in warnings)


def test_assemble_time_decomposition_ignores_suffixed_worker_names(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    strays = [run / "worker_1_backup/log_9.jsonl", run / "worker_1/log_1_old.jsonl"]
    strays[0].parent.mkdir()
    for stray in strays:
        stray.write_text('{"event": "working_start", "timestamp": 101.0}\n')
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    for stray in strays:
        assert any(
            w == f"unrecognized worker log name, ignored: {stray}" for w in warnings
        )


def test_assemble_time_decomposition_counts_undecodable_bytes_inside_strings(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    path = run / "worker_1/log_1.jsonl"
    path.write_bytes(
        path.read_bytes() + b'{"event": "work\xc3ng_start", "timestamp": 101.0}\n'
    )
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(w == f"1 malformed records skipped in {path}" for w in warnings)


def test_assemble_time_decomposition_counts_undecodable_worker_bytes(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    path = run / "worker_1/log_1.jsonl"
    path.write_bytes(
        path.read_bytes() + b'{"event": "working_start", "timestamp": 1\xc3\n'
    )
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(w == f"1 malformed records skipped in {path}" for w in warnings)


def test_assemble_time_decomposition_ignores_duplicate_worker_log_id(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    duplicate = run / "worker_3/log_1.jsonl"
    duplicate.parent.mkdir()
    duplicate.write_text(
        '{"event": "working_start", "timestamp": 103.0}\n'
        '{"event": "working_end", "timestamp": 108.0}\n'
    )
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(
        w == f"duplicate worker log id 1, ignored: {duplicate}" for w in warnings
    )


def test_assemble_time_decomposition_keeps_work_spanning_the_window(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    spanning = (
        '{"event": "working_start", "timestamp": 50.0}\n'
        '{"event": "working_end", "timestamp": 150.0}\n'
    )
    for path in (
        run / "worker_1/log_1.jsonl",
        run / "worker_2/log_3.jsonl",
        run / "worker_2/log_4.jsonl",
    ):
        path.write_text(spanning)
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == [
        30.0,
        20.0,
        0.0,
        0.0,
        0.5,
        1.0,
        0,
    ]
    assert not any("no work inside the master window" in w for w in warnings)


def test_assemble_time_decomposition_rejects_boolean_timestamps(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    path = run / "worker_1/log_1.jsonl"
    path.write_text(
        path.read_text() + '{"event": "working_start", "timestamp": true}\n'
    )
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any(w == f"1 malformed records skipped in {path}" for w in warnings)


def test_assemble_cli_reports_two_decomposition_null_causes_sorted(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_a")
    run = build_timed_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        dataset="ds_b",
        combo="atnog-test1_1_hobbit_0_samwise_0",
    )
    late_work = (
        '{"event": "working_start", "timestamp": 111.0}\n'
        '{"event": "working_end", "timestamp": 113.0}\n'
    )
    for path in (
        run / "worker_1/log_1.jsonl",
        run / "worker_2/log_3.jsonl",
        run / "worker_2/log_4.jsonl",
    ):
        path.write_text(late_work)
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    result = run_assemble_cli(
        script, results_dir, metadata_dir, hpo_dir, tmp_path / "meta_dataset.csv"
    )
    assert result.returncode == 0, result.stderr
    assert (
        "Time decomposition unavailable for 2 of 2 rows "
        "(no work inside the master window: 1, no worker logs: 1)." in result.stdout
    )


def test_assemble_time_decomposition_warns_on_absent_worker_log(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    (run / "worker_2/log_4.jsonl").unlink()
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == [
        3.5,
        2.0,
        1.25,
        0.75,
        1.0,
        1.0,
        1,
    ]
    assert any(
        "2 master send/recv events address an absent worker log" in w for w in warnings
    )


def test_assemble_time_decomposition_warns_on_unpaired_work(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    run = build_timed_run(results_dir, metadata_dir, hpo_dir)
    path = run / "worker_1/log_1.jsonl"
    path.write_text(
        path.read_text() + '{"event": "working_start", "timestamp": 109.5}\n'
    )
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any("1 worker logs with unpaired working_start/end" in w for w in warnings)


def test_assemble_cli_reports_decomposition_null_causes(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    build_timed_run(results_dir, metadata_dir, hpo_dir, dataset="ds_a")
    build_synthetic_run(
        results_dir,
        metadata_dir,
        hpo_dir,
        dataset="ds_b",
        combo="atnog-test1_1_hobbit_0_samwise_0",
    )
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    result = run_assemble_cli(
        script, results_dir, metadata_dir, hpo_dir, tmp_path / "meta_dataset.csv"
    )
    assert result.returncode == 0, result.stderr
    assert (
        "Time decomposition unavailable for 1 of 2 rows (no worker logs: 1)."
        in result.stdout
    )


def test_assemble_cli_decomposition_columns_non_empty_with_worker_logs(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    build_timed_run(results_dir, metadata_dir, hpo_dir)
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    out_csv = tmp_path / "meta_dataset.csv"
    result = run_assemble_cli(script, results_dir, metadata_dir, hpo_dir, out_csv)
    assert result.returncode == 0, result.stderr
    with open(out_csv, newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == COLUMNS
        assert reader.fieldnames[-7:] == [
            "compute_time_total_s",
            "compute_time_max_s",
            "comm_time_total_s",
            "comm_time_max_s",
            "serial_time_total_s",
            "validation_time_s",
            "comm_skew_clamped",
        ]
        row = next(reader)
    assert all(row[c] != "" for c in DECOMPOSITION_COLUMNS)


def test_assemble_time_decomposition_warns_on_unpaired_validation(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    rep_dir = build_synthetic_run(results_dir, metadata_dir, hpo_dir)
    (rep_dir / "log_0.jsonl").unlink()
    master = [
        *MASTER_EVENTS[:-1],
        {"event": "epoch", "epoch": 1, "mcc": 0.7, "timestamp": 105.0},
        {"event": "validation_start", "timestamp": 109.5},
        MASTER_EVENTS[-1],
    ]
    folder = write_run_logs(rep_dir / "2026-01-01_00:00:00", master)
    (rep_dir / "args.json").replace(folder / "args.json")
    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)
    assert [rows[0][c] for c in DECOMPOSITION_COLUMNS] == GOLDEN
    assert any("1 validation_start/end events unpaired" in w for w in warnings)


def test_assembler_import_is_stdlib_only():
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "import assemble_meta_dataset; "
            "assert 'pandas' not in sys.modules and 'numpy' not in sys.modules",
            str(scripts),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


# --- epoch cap ---


def test_assemble_records_the_epoch_cap(tmp_path):
    build_synthetic_run(tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo")
    rows, warnings = assemble(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    assert [row["epoch_cap"] for row in rows] == [200]
    assert COLUMNS.index("epoch_cap") == COLUMNS.index("local_epochs") + 1


def test_assemble_reads_the_cap_beside_the_master_log(tmp_path):
    folder = build_timed_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo", epoch_cap=7
    )
    assert (folder / "args.json").exists()
    rows, warnings = assemble(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    assert [row["epoch_cap"] for row in rows] == [7]


def test_assemble_prefers_the_recorded_cap_over_the_sampled_one(tmp_path):
    build_synthetic_run(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        epoch_cap=5,
        hyperparameters={
            "learning_rate": 0.001,
            "batch_size": 256,
            "patience": 3,
            "delta": 0.01,
            "epochs": 200,
        },
    )
    rows, warnings = assemble(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    assert [row["epoch_cap"] for row in rows] == [5]


@pytest.mark.parametrize(
    "args, missing",
    [
        (None, "no args.json beside the master log"),
        ({"fl": "cs"}, "args.json has no epochs"),
        (["epochs", 200], "args.json is not a JSON object"),
    ],
)
def test_assemble_drops_a_run_without_a_recorded_cap(tmp_path, args, missing):
    rep_dir = build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo", epoch_cap=None
    )
    if args is not None:
        write_json(rep_dir / "args.json", args)
    rows, warnings = assemble(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    assert rows == []
    assert warnings == [f"no recorded epoch cap ({missing}), skipped: {rep_dir}"]


@pytest.mark.parametrize("args", [None, {"fl": "cs"}])
def test_assemble_legacy_epoch_cap_fills_a_missing_cap(tmp_path, args):
    rep_dir = build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo", epoch_cap=None
    )
    if args is not None:
        write_json(rep_dir / "args.json", args)
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_epoch_cap=10,
        legacy_early_stop_rule=True,
    )
    assert [row["epoch_cap"] for row in rows] == [10]


@pytest.mark.parametrize("value", ["200", 0, -1, True, 2.5])
def test_assemble_drops_an_invalid_recorded_cap(tmp_path, value):
    rep_dir = build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo", epoch_cap=value
    )
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_epoch_cap=10,
    )
    assert rows == []
    assert warnings == [f"invalid epoch cap {value!r} in args.json, skipped: {rep_dir}"]


def test_assemble_drops_a_null_recorded_cap_even_with_a_legacy_cap(tmp_path):
    rep_dir = build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo", epoch_cap=None
    )
    write_json(rep_dir / "args.json", {"epochs": None})
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_epoch_cap=10,
    )
    assert rows == []
    assert warnings == [f"invalid epoch cap None in args.json, skipped: {rep_dir}"]


def test_assemble_ignores_a_cap_only_in_hyperparameters_json(tmp_path):
    rep_dir = build_synthetic_run(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        epoch_cap=None,
        hyperparameters={
            "learning_rate": 0.001,
            "batch_size": 256,
            "patience": 3,
            "delta": 0.01,
            "epochs": 200,
        },
    )
    rows, warnings = assemble(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    assert rows == []
    assert warnings == [
        "no recorded epoch cap (no args.json beside the master log), "
        f"skipped: {rep_dir}"
    ]


@pytest.mark.parametrize("content", [b"{not json", b"\xff\xfe"])
def test_assemble_skips_a_run_with_an_unreadable_args_json(tmp_path, content):
    rep_dir = build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo", dataset="ds_b"
    )
    (rep_dir / "args.json").write_bytes(content)
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_epoch_cap=10,
    )
    assert [row["dataset"] for row in rows] == ["ds_b"]
    cap_warnings = [w for w in warnings if "args.json" in w]
    assert len(cap_warnings) == 1
    assert cap_warnings[0].startswith("unreadable args.json (")
    assert cap_warnings[0].endswith(f"), skipped: {rep_dir}")


def _run_assembler_cli(tmp_path, *extra):
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )
    return subprocess.run(
        [
            sys.executable,
            script,
            "--results-dir",
            str(tmp_path / "results"),
            "--metadata-dir",
            str(tmp_path / "metadata"),
            "--hpo-dir",
            str(tmp_path / "hpo"),
            "--out",
            str(tmp_path / "meta_dataset.csv"),
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def test_assemble_cli_legacy_epoch_cap_writes_the_column(tmp_path):
    build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo", epoch_cap=None
    )
    assert _run_assembler_cli(tmp_path).returncode == 0
    with open(tmp_path / "meta_dataset.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == 0
    assert (
        _run_assembler_cli(
            tmp_path, "--legacy-epoch-cap", "10", "--legacy-early-stop-rule"
        ).returncode
        == 0
    )
    with open(tmp_path / "meta_dataset.csv", newline="") as f:
        assert [row["epoch_cap"] for row in csv.DictReader(f)] == ["10"]


def test_assemble_cli_rejects_a_non_positive_legacy_epoch_cap(tmp_path):
    build_synthetic_run(tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo")
    result = _run_assembler_cli(tmp_path, "--legacy-epoch-cap", "0")
    assert result.returncode == 2
    assert "--legacy-epoch-cap must be a positive integer" in result.stderr


# --- early-stop rule ---


def test_assemble_records_the_early_stop_rule(tmp_path):
    build_synthetic_run(tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo")
    build_synthetic_run(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        dataset="ds_b",
        early_stop_rule=("metric", 0),
    )
    rows, warnings = assemble(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    assert [
        (row["dataset"], row["early_stop_on"], row["min_epochs"]) for row in rows
    ] == [("ds_a", "loss", 10), ("ds_b", "metric", 0)]
    assert COLUMNS.index("early_stop_on") == COLUMNS.index("epoch_cap") + 1
    assert COLUMNS.index("min_epochs") == COLUMNS.index("early_stop_on") + 1


def test_assemble_reads_the_rule_beside_the_master_log(tmp_path):
    folder = build_timed_run(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        early_stop_rule=("metric", 3),
    )
    assert (folder / "args.json").exists()
    rows, warnings = assemble(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    assert [(row["early_stop_on"], row["min_epochs"]) for row in rows] == [
        ("metric", 3)
    ]


def test_assemble_drops_a_run_without_a_recorded_rule(tmp_path):
    rep_dir = build_synthetic_run(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        early_stop_rule=None,
    )
    rows, warnings = assemble(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    assert rows == []
    assert warnings == [
        "no recorded early-stop rule (args.json has no early_stop_on/min_epochs), "
        f"skipped: {rep_dir}"
    ]


@pytest.mark.parametrize(
    "args, missing",
    [
        (None, "no args.json beside the master log"),
        (["epochs", 200], "args.json is not a JSON object"),
    ],
)
def test_assemble_drops_a_run_without_a_usable_args_json_for_the_rule(
    tmp_path, args, missing
):
    rep_dir = build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo", epoch_cap=None
    )
    if args is not None:
        write_json(rep_dir / "args.json", args)
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_epoch_cap=10,
    )
    assert rows == []
    assert warnings == [f"no recorded early-stop rule ({missing}), skipped: {rep_dir}"]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "args, shown",
    [
        ({"epochs": 200, "early_stop_on": "loss"}, ("loss", None)),
        ({"epochs": 200, "min_epochs": 10}, (None, 10)),
        ({"epochs": 200, "early_stop_on": "mcc"}, ("mcc", None)),
    ],
)
def test_assemble_drops_a_partly_recorded_rule_even_with_the_legacy_flag(
    tmp_path, legacy, args, shown
):
    rep_dir = build_synthetic_run(
        tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo"
    )
    write_json(rep_dir / "args.json", args)
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_early_stop_rule=legacy,
    )
    assert rows == []
    assert warnings == [
        f"invalid early-stop rule ({shown[0]!r}, {shown[1]!r}) in args.json, "
        f"skipped: {rep_dir}"
    ]


def test_assemble_legacy_rule_fills_a_missing_rule(tmp_path):
    build_synthetic_run(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        early_stop_rule=None,
    )
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_early_stop_rule=True,
    )
    assert [(row["early_stop_on"], row["min_epochs"]) for row in rows] == [
        ("metric", 0)
    ]


def test_assemble_legacy_rule_does_not_override_a_recorded_rule(tmp_path):
    build_synthetic_run(tmp_path / "results", tmp_path / "metadata", tmp_path / "hpo")
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_early_stop_rule=True,
    )
    assert [(row["early_stop_on"], row["min_epochs"]) for row in rows] == [("loss", 10)]


@pytest.mark.parametrize(
    "rule",
    [
        ("mcc", 10),
        ("loss", -1),
        ("loss", 2.5),
        ("loss", True),
        ("loss", None),
        (None, 10),
    ],
)
def test_assemble_drops_an_invalid_recorded_rule(tmp_path, rule):
    rep_dir = build_synthetic_run(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        early_stop_rule=rule,
    )
    rows, warnings = assemble(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        legacy_early_stop_rule=True,
    )
    assert rows == []
    assert warnings == [
        f"invalid early-stop rule ({rule[0]!r}, {rule[1]!r}) in args.json, "
        f"skipped: {rep_dir}"
    ]


def test_assemble_cli_legacy_rule_writes_the_columns(tmp_path):
    build_synthetic_run(
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        early_stop_rule=None,
    )
    assert _run_assembler_cli(tmp_path).returncode == 0
    with open(tmp_path / "meta_dataset.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == 0
    assert _run_assembler_cli(tmp_path, "--legacy-early-stop-rule").returncode == 0
    with open(tmp_path / "meta_dataset.csv", newline="") as f:
        assert [
            (row["early_stop_on"], row["min_epochs"]) for row in csv.DictReader(f)
        ] == [("metric", "0")]


# --- constant-mean baseline (regression) ---


def build_regression_run(
    results_dir: Path,
    metadata_dir: Path,
    hpo_dir: Path,
    mapes,
    *,
    dataset="reg_ds",
    **kwargs,
):
    rep_dir = build_synthetic_run(
        results_dir, metadata_dir, hpo_dir, dataset=dataset, **kwargs
    )
    events = [{"event": "start", "timestamp": 0}]
    events += [
        {"event": "epoch", "epoch": i, "mape": m} for i, m in enumerate(mapes, 1)
    ]
    events.append({"event": "end", "timestamp": 5})
    write_jsonl(rep_dir / "log_0.jsonl", events)
    write_json(
        metadata_dir / f"{dataset}.json",
        {
            "type": "regression",
            "input_shape": [4],
            "samples": 100,
            "output_size": 1,
        },
    )
    return rep_dir


def write_target_cache(data_dir: Path, dataset: str, y_train, y_val):
    import numpy as np

    cache = data_dir / dataset / "_data"
    cache.mkdir(parents=True, exist_ok=True)
    np.save(cache / "y_train.npy", np.asarray(y_train))
    np.save(cache / "y_val.npy", np.asarray(y_val))


# train mean 2.5 against val [1, 2, 4]; an integer mean would give 2.
BASELINE = (6 / 7 + 2 / 9 + 6 / 13) / 3


def test_constant_mean_smape_matches_hand_computed_value(tmp_path):
    write_target_cache(tmp_path, "reg_ds", [1, 4], [1, 2, 4])

    value, reason = constant_mean_smape(tmp_path, "reg_ds")

    assert reason is None
    assert value == pytest.approx(BASELINE, rel=1e-12)


def test_constant_mean_smape_accepts_single_column_targets(tmp_path):
    write_target_cache(tmp_path, "reg_ds", [[1.0], [4.0]], [[1.0], [2.0], [4.0]])

    value, reason = constant_mean_smape(tmp_path, "reg_ds")

    assert reason is None
    assert value == pytest.approx(BASELINE, rel=1e-12)


def test_constant_mean_smape_zero_targets_score_zero(tmp_path):
    write_target_cache(tmp_path, "reg_ds", [0.0, 0.0], [0.0, 0.0])

    assert constant_mean_smape(tmp_path, "reg_ds") == (0.0, None)


@pytest.mark.parametrize(
    "y_train, y_val, reason",
    [
        ([1.0, 2.0], [], "y_val.npy is not a non-empty single real target"),
        ([1.0, float("nan")], [1.0], "y_train.npy has non-finite targets"),
        ([[1.0, 2.0]], [1.0], "y_train.npy is not a non-empty single real target"),
        ([True, False], [1.0], "y_train.npy is not a non-empty single real target"),
    ],
)
def test_constant_mean_smape_rejects_invalid_targets(tmp_path, y_train, y_val, reason):
    write_target_cache(tmp_path, "reg_ds", y_train, y_val)

    assert constant_mean_smape(tmp_path, "reg_ds") == (None, reason)


def test_constant_mean_smape_rejects_pickled_targets(tmp_path):
    import numpy as np

    cache = tmp_path / "reg_ds" / "_data"
    cache.mkdir(parents=True)
    np.save(cache / "y_train.npy", np.array([{"a": 1}], dtype=object))
    np.save(cache / "y_val.npy", np.array([1.0]))

    value, reason = constant_mean_smape(tmp_path, "reg_ds")

    assert value is None
    assert reason.startswith("unreadable y_train.npy")


def test_constant_mean_smape_rejects_npz_archive(tmp_path):
    import numpy as np

    cache = tmp_path / "reg_ds" / "_data"
    cache.mkdir(parents=True)
    with open(cache / "y_train.npy", "wb") as f:
        np.savez(f, y=np.array([1.0, 4.0]))
    np.save(cache / "y_val.npy", np.array([1.0]))

    assert constant_mean_smape(tmp_path, "reg_ds") == (
        None,
        "y_train.npy is not a .npy array",
    )


def test_constant_mean_smape_missing_cache(tmp_path):
    value, reason = constant_mean_smape(tmp_path, "reg_ds")

    assert value is None
    assert reason.startswith("missing y_train.npy, y_val.npy in ")


def test_assemble_flags_regression_rows_against_baseline_and_keeps_them(tmp_path):
    results_dir, metadata_dir, hpo_dir, data_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        tmp_path / "data",
    )
    write_target_cache(data_dir, "reg_ds", [1, 4], [1, 2, 4])
    for rep, best in enumerate((BASELINE - 0.01, BASELINE, BASELINE + 0.01), 1):
        build_regression_run(
            results_dir, metadata_dir, hpo_dir, [best + 0.2, best, best + 0.1], rep=rep
        )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir, data_dir=data_dir)

    by_rep = {r["repeat"]: r for r in rows}
    assert [by_rep[r]["beats_constant_mean"] for r in (1, 2, 3)] == [
        True,
        False,
        False,
    ]
    assert all(
        r["constant_mean_smape"] == pytest.approx(BASELINE, rel=1e-12) for r in rows
    )
    assert not any("constant-mean baseline" in w for w in warnings)


def test_assemble_leaves_baseline_empty_for_classification(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    build_synthetic_run(results_dir, metadata_dir, hpo_dir)

    rows, warnings = assemble(
        results_dir, metadata_dir, hpo_dir, data_dir=tmp_path / "data"
    )

    assert rows[0]["constant_mean_smape"] is None
    assert rows[0]["beats_constant_mean"] is None
    assert not any("constant-mean baseline" in w for w in warnings)


def test_assemble_missing_baseline_keeps_rows_and_warns_once_per_dataset(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    for rep in (1, 2):
        build_regression_run(results_dir, metadata_dir, hpo_dir, [0.3], rep=rep)

    rows, warnings = assemble(
        results_dir, metadata_dir, hpo_dir, data_dir=tmp_path / "data"
    )

    assert len(rows) == 2
    assert all(
        r["constant_mean_smape"] is None and r["beats_constant_mean"] is None
        for r in rows
    )
    baseline_warnings = [w for w in warnings if "constant-mean baseline" in w]
    assert len(baseline_warnings) == 1
    assert "reg_ds" in baseline_warnings[0]


def test_assemble_keeps_rows_when_numpy_or_flexfl_cannot_import(tmp_path, monkeypatch):
    results_dir, metadata_dir, hpo_dir, data_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        tmp_path / "data",
    )
    write_target_cache(data_dir, "reg_ds", [1, 4], [1, 2, 4])
    for rep in (1, 2):
        build_regression_run(results_dir, metadata_dir, hpo_dir, [0.3], rep=rep)
    monkeypatch.setitem(sys.modules, "flexfl.builtins.FederatedABC", None)

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir, data_dir=data_dir)

    assert len(rows) == 2
    assert all(
        r["constant_mean_smape"] is None and r["beats_constant_mean"] is None
        for r in rows
    )
    baseline_warnings = [w for w in warnings if "constant-mean baseline" in w]
    assert len(baseline_warnings) == 1
    assert "cannot import numpy or flexfl" in baseline_warnings[0]


def test_assemble_without_data_dir_warns_no_data_dir(tmp_path):
    results_dir, metadata_dir, hpo_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
    )
    build_regression_run(results_dir, metadata_dir, hpo_dir, [0.3])

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["constant_mean_smape"] is None
    assert any("(no data dir given)" in w for w in warnings)


def test_assemble_cli_writes_baseline_columns_from_data_dir(tmp_path):
    results_dir, metadata_dir, hpo_dir, data_dir = (
        tmp_path / "results",
        tmp_path / "metadata",
        tmp_path / "hpo",
        tmp_path / "data",
    )
    write_target_cache(data_dir, "reg_ds", [1, 4], [1, 2, 4])
    build_regression_run(results_dir, metadata_dir, hpo_dir, [0.3])
    out_csv = tmp_path / "meta_dataset.csv"
    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            script,
            "--results-dir",
            str(results_dir),
            "--metadata-dir",
            str(metadata_dir),
            "--hpo-dir",
            str(hpo_dir),
            "--data-dir",
            str(data_dir),
            "--out",
            str(out_csv),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    with open(out_csv, newline="") as f:
        row = next(csv.DictReader(f))
    assert float(row["constant_mean_smape"]) == pytest.approx(BASELINE, rel=1e-12)
    assert row["beats_constant_mean"] == "True"
