import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from assemble_meta_dataset import (
    COLUMNS,
    assemble,
    compute_targets,
    parse_combo,
    worker_compute,
)


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_jsonl(path: Path, events: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


# --- parse_combo ---

def test_parse_combo_valid():
    result = parse_combo("atnog-test1_2_hobbit_4_samwise_8")
    assert (result["n_atnog_test1"], result["n_hobbit"], result["n_samwise"]) == (2, 4, 8)


def test_parse_combo_missing_node_token():
    result = parse_combo("atnog-test1_2_hobbit_4")
    assert result["n_samwise"] is None


# --- compute_targets ---

def test_compute_targets_classification_takes_max_mcc():
    events = [
        {"event": "start", "timestamp": 1000},
        {"event": "epoch", "mcc": 0.5},
        {"event": "epoch", "mcc": 0.8},
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
        {"event": "epoch", "mape": 0.3},
        {"event": "epoch", "mape": 0.1},
        {"event": "end", "timestamp": 5},
    ]
    result = compute_targets(events, is_classification=False)
    assert result["performance"] == 0.1
    assert result["main_metric"] == "mape"


def test_compute_targets_none_when_missing_start_or_end_or_epoch():
    assert compute_targets([{"event": "start", "timestamp": 0}], is_classification=True) is None
    assert compute_targets([{"event": "end", "timestamp": 0}], is_classification=True) is None
    assert compute_targets(
        [{"event": "start", "timestamp": 0}, {"event": "end", "timestamp": 1}], is_classification=True
    ) is None


def test_compute_targets_none_when_no_epoch_has_numeric_main_metric():
    events = [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "mcc": None},
        {"event": "end", "timestamp": 1},
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
        "10.0.0.1 frodo 104\n"
        "10.0.0.2 hobbit 108\n"
        "10.0.0.3 samwise 106\n"
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
        "10.0.0.1 frodo 104\n"
        "10.0.0.2 hobbit 108\n"
        "10.0.0.3 samwise 999\n"
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
        "10.0.0.1 frodo 104\n"
        "10.0.0.2 hobbit 108\n"
        "10.0.0.3 samwise 999\n"
    )

    result = worker_compute(workers_txt, benchmark_dir)

    assert result["n_workers"] == 2
    assert result["n_workers_benchmarked"] == 2
    assert result["worker_rate_mean"] == 3.0


def test_worker_compute_different_nodes_sharing_vmid_resolve_to_different_files(tmp_path):
    benchmark_dir = tmp_path / "benchmark"
    make_benchmark_file(benchmark_dir, "hobbit", "100", 2.0)
    make_benchmark_file(benchmark_dir, "atnog-test1", "100", 6.0)
    workers_txt = tmp_path / "workers.txt"
    workers_txt.write_text(
        "10.0.0.1 frodo 104\n"
        "10.0.0.2 hobbit 100\n"
        "10.0.0.3 atnog-test1 100\n"
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
        "10.0.0.1 frodo 104\n"
        "10.0.0.9 hobbit 108\n"
        "10.0.0.9 samwise 106\n"
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
    results_dir: Path, metadata_dir: Path, hpo_dir: Path, *,
    strategy="iid", combo="atnog-test1_0_hobbit_1_samwise_0",
    dataset="ds_a", fl_algo="CentralizedSync", rep=1,
    sentinel="_SUCCESS", with_epochs=True, workers_txt=None, with_hpo=True,
    hyperparameters=None, new_workers=0,
):
    rep_dir = results_dir / strategy / combo / dataset / fl_algo / f"rep_{rep}"
    rep_dir.mkdir(parents=True, exist_ok=True)

    events = [
        {"event": "new_worker", "node_id": i, "info": {}}
        for i in range(1, new_workers + 1)
    ]
    events.append({"event": "start", "timestamp": 0})
    if with_epochs:
        events.append({"event": "epoch", "mcc": 0.7})
    events.append({"event": "end", "timestamp": 5})
    write_jsonl(rep_dir / "log_0.jsonl", events)

    (rep_dir / sentinel).write_text("")

    if workers_txt is not None:
        (rep_dir.parent.parent.parent / "workers.txt").write_text(workers_txt)

    write_json(metadata_dir / f"{dataset}.json", {
        "type": "classification", "input_shape": [4], "samples": 100, "output_size": 2,
    })
    if with_hpo:
        write_json(hpo_dir / f"{dataset}.json", {
            "n_layers": 2, "n_units_l0": 8, "n_units_l1": 4, "weight_decay": 0.001,
        })
    if hyperparameters is not None:
        write_json(rep_dir / "hyperparameters.json", hyperparameters)
    return rep_dir


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
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, workers_txt="10.0.0.1\n10.0.0.2\n")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    assert any("legacy IP-only workers.txt, worker compute skipped" in w for w in warnings)


def test_assemble_incomplete_worker_benchmark_warns(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    make_benchmark_file(results_dir / "benchmark", "hobbit", "108", 2.0)
    build_synthetic_run(
        results_dir, metadata_dir, hpo_dir,
        workers_txt=(
            "10.0.0.1 frodo 104\n"
            "10.0.0.2 hobbit 108\n"
            "10.0.0.3 samwise 999\n"
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
    rep_dir = results_dir / "iid" / "atnog-test1_0_hobbit_1_samwise_0" / "ds_a" / "fedavg" / "rep_1"
    rep_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(rep_dir / "log_0.jsonl", [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "mcc": float("nan")},
        {"event": "end", "timestamp": 5},
    ])
    (rep_dir / "_SUCCESS").write_text("")
    write_json(metadata_dir / "ds_a.json", {
        "type": "classification", "input_shape": [4], "samples": 100, "output_size": 2,
    })
    write_json(hpo_dir / "ds_a.json", {
        "n_layers": 2, "n_units_l0": 8, "n_units_l1": 4, "weight_decay": 0.001,
    })

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows == []
    assert any("targets uncomputable" in w for w in warnings)

    out_csv = tmp_path / "meta_dataset.csv"
    script = str(Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py")
    result = subprocess.run(
        [sys.executable, script,
         "--results-dir", str(results_dir),
         "--metadata-dir", str(metadata_dir),
         "--hpo-dir", str(hpo_dir),
         "--out", str(out_csv)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    with open(out_csv, newline="") as f:
        lines = list(csv.reader(f))
    assert len(lines) == 1  # header only, no data row for the NaN run
    assert "targets uncomputable" in result.stderr
    assert "no HPO config" not in result.stderr


def run_assemble_cli(script: str, results_dir: Path, metadata_dir: Path, hpo_dir: Path, out_csv: Path):
    return subprocess.run(
        [sys.executable, script,
         "--results-dir", str(results_dir),
         "--metadata-dir", str(metadata_dir),
         "--hpo-dir", str(hpo_dir),
         "--out", str(out_csv)],
        capture_output=True, text=True,
    )


def test_assemble_idempotent_byte_identical_over_growing_tree(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_a")
    script = str(Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py")

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
        results_dir, metadata_dir, hpo_dir, dataset="ds_b", combo="atnog-test1_1_hobbit_0_samwise_0"
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

    script = str(Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py")
    result = subprocess.run(
        [sys.executable, script,
         "--results-dir", str(results_dir),
         "--metadata-dir", str(metadata_dir),
         "--hpo-dir", str(hpo_dir),
         "--out", str(out_csv)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    with open(out_csv, newline="") as f:
        lines = list(csv.reader(f))
    assert lines[0] == COLUMNS
    assert len(lines) == 2  # header + 1 data row


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
    results_dir: Path, metadata_dir: Path, hpo_dir: Path, dataset: str, metadata: dict, hpo: dict,
    combo="atnog-test1_0_hobbit_1_samwise_0", fl_algo="fedavg", rep=1,
):
    rep_dir = results_dir / "iid" / combo / dataset / fl_algo / f"rep_{rep}"
    rep_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(rep_dir / "log_0.jsonl", [
        {"event": "start", "timestamp": 0},
        {"event": "epoch", "mcc": 0.7},
        {"event": "end", "timestamp": 5},
    ])
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
        results_dir, metadata_dir, hpo_dir, "ds_bad",
        {"type": "classification", "samples": 100, "output_size": 2},  # no input_shape -> n_features None
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
        results_dir, metadata_dir, hpo_dir, "ds_bad",
        {"type": "classification", "input_shape": [4], "samples": 100, "output_size": 2},
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
        results_dir, metadata_dir, hpo_dir, "ds_bad",
        {"type": "classification", "input_shape": [4], "samples": 100, "output_size": 2},
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
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_without_hpo", with_hpo=False)

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert len(rows) == 1
    row = rows[0]
    assert row["dataset"] == "ds_with_hpo"
    for col in ("total_parameters", "n_layers", "mean_layer_width", "max_layer_width", "weight_decay"):
        assert row[col] is not None
    assert any("no HPO config for ds_without_hpo" in w for w in warnings)


def test_assemble_cli_no_hpo_config_skip_does_not_crash(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, dataset="ds_no_hpo", with_hpo=False)

    out_csv = tmp_path / "meta_dataset.csv"
    script = str(Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py")
    result = subprocess.run(
        [sys.executable, script,
         "--results-dir", str(results_dir),
         "--metadata-dir", str(metadata_dir),
         "--hpo-dir", str(hpo_dir),
         "--out", str(out_csv)],
        capture_output=True, text=True,
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
        results_dir, metadata_dir, hpo_dir, fl_algo="CentralizedSync",
        hyperparameters={
            "learning_rate": 0.001, "batch_size": 256, "patience": 5, "delta": 0.01,
        },
    )
    out_csv = tmp_path / "meta_dataset.csv"
    script = str(Path(__file__).resolve().parent.parent / "scripts" / "assemble_meta_dataset.py")
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
        results_dir, metadata_dir, hpo_dir, fl_algo=fl_algo,
        hyperparameters={
            "learning_rate": 0.001, "batch_size": 256, "patience": 5, "delta": 0.01,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    row = rows[0]
    assert (row["learning_rate"], row["batch_size"], row["patience"], row["delta"], row["local_epochs"]) == (0.001, 256, 5, 0.01, 0)


def test_assemble_local_epochs_preserves_sampled_value_for_decentralized(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir, metadata_dir, hpo_dir, fl_algo="DecentralizedSync",
        hyperparameters={
            "learning_rate": 0.001, "batch_size": 256, "patience": 5,
            "delta": 0.01, "local_epochs": 7,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] == 7


def test_assemble_local_epochs_stays_null_when_genuinely_missing_for_decentralized(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, fl_algo="DecentralizedSync")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] is None
    assert any("local_epochs unrecorded" in w for w in warnings)


def test_assemble_local_epochs_zero_and_warns_when_no_hyperparameters_recorded_for_centralized(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, fl_algo="CentralizedSync")

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] == 0
    assert any("no FL hyperparameters recorded" in w for w in warnings)


@pytest.mark.parametrize("fl_algo", ("cs", "ca"))
def test_assemble_local_epochs_zero_for_centralized_alias_directory_names(tmp_path, fl_algo):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir, metadata_dir, hpo_dir, fl_algo=fl_algo,
        hyperparameters={
            "learning_rate": 0.001, "batch_size": 256, "patience": 5, "delta": 0.01,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] == 0


@pytest.mark.parametrize("fl_algo", ("CENTRALIZEDSYNC", "Cs"))
def test_assemble_local_epochs_zero_for_centralized_mixed_case_directory_names(tmp_path, fl_algo):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(
        results_dir, metadata_dir, hpo_dir, fl_algo=fl_algo,
        hyperparameters={
            "learning_rate": 0.001, "batch_size": 256, "patience": 5, "delta": 0.01,
        },
    )

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["local_epochs"] == 0


FL_ALGOS = ("CentralizedSync", "CentralizedAsync", "DecentralizedSync", "DecentralizedAsync")
STRATEGIES = ("iid", "non_iid", "dirichlet")


@pytest.mark.parametrize("fl_algo", FL_ALGOS)
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_assemble_onehot_fl_algo_and_strategy(tmp_path, strategy, fl_algo):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    build_synthetic_run(results_dir, metadata_dir, hpo_dir, strategy=strategy, fl_algo=fl_algo)

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
    assert any("unrecognized strategy" in w and "extreme_non_iid" in w for w in warnings)


@pytest.mark.parametrize("fl_algo,canonical", (
    ("cs", "CentralizedSync"), ("ca", "CentralizedAsync"),
    ("ds", "DecentralizedSync"), ("da", "DecentralizedAsync"),
    ("CENTRALIZEDSYNC", "CentralizedSync"), ("Cs", "CentralizedSync"),
))
def test_assemble_onehot_resolves_fl_algo_aliases_and_case_variants(tmp_path, fl_algo, canonical):
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
    write_json(rep_dir.parent.parent / "division.json", {"strategy": "iid", "num_workers": 4})

    rows, warnings = assemble(results_dir, metadata_dir, hpo_dir)

    assert rows[0]["n_workers_joined"] == 4
    assert rows[0]["n_workers_joined"] == rows[0]["num_workers"]


def test_assemble_n_workers_joined_below_num_workers_on_short_pool(tmp_path):
    results_dir = tmp_path / "results"
    metadata_dir = tmp_path / "metadata"
    hpo_dir = tmp_path / "hpo"
    rep_dir = build_synthetic_run(results_dir, metadata_dir, hpo_dir, new_workers=3)
    write_json(rep_dir.parent.parent / "division.json", {"strategy": "iid", "num_workers": 4})

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
