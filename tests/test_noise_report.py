import csv
import math
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "noise_report.py"

IDENTITY = ("strategy", "combo", "dataset", "fl_algo", "repeat")
HP_DEFAULTS = {
    "learning_rate": "0.01",
    "batch_size": "32",
    "local_epochs": "2",
    "patience": "5",
    "delta": "0.001",
    "epoch_cap": "200",
    "early_stop_on": "loss",
    "min_epochs": "3",
}
TARGETS = (
    "performance",
    "total_time_s",
    "comm_bytes_total",
    "n_epochs",
    "compute_time_total_s",
    "compute_time_max_s",
    "comm_time_total_s",
    "comm_time_max_s",
    "serial_time_total_s",
    "validation_time_s",
)
COLUMNS = IDENTITY + tuple(HP_DEFAULTS) + ("is_classification",) + TARGETS


def make_row(index, repeat=1, is_clf="True", hp=None, **targets):
    row = {
        "strategy": "iid",
        "combo": "atnog-test1_2_hobbit_4_samwise_8",
        "dataset": f"ds{index}",
        "fl_algo": "CentralizedSync",
        "repeat": str(repeat),
        "is_classification": is_clf,
    }
    row.update(HP_DEFAULTS)
    row.update(hp or {})
    row.update({name: "1.0" for name in TARGETS})
    row.update({name: str(value) for name, value in targets.items()})
    return row


def write_csv(path, rows):
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_report(tmp_path, original_rows, rerun_rows, out_dir=None):
    original = write_csv(tmp_path / "original.csv", original_rows)
    rerun = write_csv(tmp_path / "rerun.csv", rerun_rows)
    out = out_dir if out_dir is not None else tmp_path / "out"
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--original",
            str(original),
            "--rerun",
            str(rerun),
            "--out-dir",
            str(out),
        ],
        capture_output=True,
        text=True,
    )


def read_rows(path):
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def summary_row(out, target, cohort="all"):
    matches = [
        row
        for row in read_rows(out / "noise_summary.csv")
        if row["target"] == target and row["cohort"] == cohort
    ]
    assert len(matches) == 1, (target, cohort, matches)
    return matches[0]


def time_rows(originals, reruns):
    return (
        [make_row(i, total_time_s=v) for i, v in enumerate(originals)],
        [make_row(i, total_time_s=v) for i, v in enumerate(reruns)],
    )


def plain_expected(originals, reruns):
    cvs, variances, means = [], [], []
    for a, b in zip(originals, reruns):
        mean = (a + b) / 2
        sd = abs(a - b) / math.sqrt(2)
        variances.append(sd**2)
        means.append(abs(mean))
        cvs.append(sd / abs(mean))

    def r_squared(truth, pred):
        avg = sum(truth) / len(truth)
        ss_res = sum((t - p) ** 2 for t, p in zip(truth, pred))
        ss_tot = sum((t - avg) ** 2 for t in truth)
        return 1 - ss_res / ss_tot

    expected = {
        "cv_median": statistics.median(cvs),
        "cv_mean": statistics.mean(cvs),
        "cv_pooled": math.sqrt(statistics.mean(variances)) / statistics.mean(means),
        "r2_raw": r_squared(originals, reruns),
    }
    if min(originals + reruns) >= 0:
        expected["r2_log1p"] = r_squared(
            [math.log1p(v) for v in originals], [math.log1p(v) for v in reruns]
        )
    else:
        expected["r2_log1p"] = "NA"
    return expected


def test_single_pair_cv_matches_definition(tmp_path):
    result = run_report(tmp_path, *time_rows([10], [12]))
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    expected_cv = abs(2) / math.sqrt(2) / 11
    assert row["n_pairs"] == "1"
    assert float(row["cv_median"]) == pytest.approx(expected_cv)
    assert float(row["cv_mean"]) == pytest.approx(expected_cv)
    assert float(row["cv_pooled"]) == pytest.approx(expected_cv)
    assert row["r2_raw"] == "NA"
    assert row["r2_log1p"] == "NA"


def test_identical_files_give_zero_cv_and_unit_r2(tmp_path):
    rows, same = time_rows([10, 20, 30], [10, 20, 30])
    result = run_report(tmp_path, rows, same)
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    assert float(row["cv_median"]) == 0
    assert float(row["cv_mean"]) == 0
    assert float(row["cv_pooled"]) == 0
    assert float(row["r2_raw"]) == pytest.approx(1)
    assert float(row["r2_log1p"]) == pytest.approx(1)


def test_zero_mean_pairs_give_na_cv(tmp_path):
    result = run_report(tmp_path, *time_rows([0, 0], [0, 0]))
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    assert row["cv_median"] == "NA"
    assert row["cv_mean"] == "NA"
    assert row["cv_pooled"] == "NA"


def test_pooled_cv_includes_zero_sum_pairs(tmp_path):
    result = run_report(tmp_path, *time_rows([1, -0.5], [1, 0.5]))
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    assert float(row["cv_pooled"]) == pytest.approx(1.0)


def test_constant_original_gives_na_r2(tmp_path):
    result = run_report(tmp_path, *time_rows([7, 7, 7], [6, 7, 8]))
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    assert row["n_pairs"] == "3"
    assert row["r2_raw"] == "NA"
    assert row["r2_log1p"] == "NA"
    assert float(row["cv_mean"]) > 0


def test_negative_target_gives_na_log1p_only(tmp_path):
    result = run_report(tmp_path, *time_rows([-10, 20, 30], [-12, 18, 33]))
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    assert row["r2_log1p"] == "NA"
    assert float(row["r2_raw"]) == pytest.approx(
        plain_expected([-10, 20, 30], [-12, 18, 33])["r2_raw"]
    )


def test_hp_mismatch_and_missing_rerun_are_counted_and_excluded(tmp_path):
    originals = [make_row(i, total_time_s=10 * (i + 1)) for i in range(4)]
    reruns = [
        make_row(0, total_time_s=11),
        make_row(1, total_time_s=21, hp={"learning_rate": "0.02"}),
        make_row(2, total_time_s=33),
    ]
    result = run_report(tmp_path, originals, reruns)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "out"
    row = summary_row(out, "total_time_s")
    assert row["n_pairs"] == "2"
    assert row["n_excluded"] == "2"
    reasons = {
        pair["dataset"]: pair["reason"]
        for pair in read_rows(out / "noise_pairs.csv")
        if pair["target"] == "total_time_s"
    }
    assert reasons == {
        "ds0": "included",
        "ds1": "hp_mismatch",
        "ds2": "included",
        "ds3": "missing_rerun",
    }


def test_nan_hyperparameter_equals_nan(tmp_path):
    originals = [make_row(0, hp={"delta": ""}, total_time_s=10)]
    reruns = [make_row(0, hp={"delta": "nan"}, total_time_s=12)]
    result = run_report(tmp_path, originals, reruns)
    assert result.returncode == 0, result.stderr
    assert summary_row(tmp_path / "out", "total_time_s")["n_pairs"] == "1"


@pytest.mark.parametrize("column", sorted(HP_DEFAULTS))
def test_every_hyperparameter_column_gates_the_pair(tmp_path, column):
    changed = "other" if column == "early_stop_on" else "999"
    originals = [make_row(0, total_time_s=10)]
    reruns = [make_row(0, hp={column: changed}, total_time_s=12)]
    result = run_report(tmp_path, originals, reruns)
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    assert row["n_pairs"] == "0"
    assert row["n_excluded"] == "1"


def test_performance_is_split_by_cohort(tmp_path):
    originals = [
        make_row(0, is_clf="True", performance=0.5),
        make_row(1, is_clf="True", performance=0.6),
        make_row(2, is_clf="False", performance=20),
        make_row(3, is_clf="False", performance=30),
        make_row(4, is_clf="False", performance=40),
    ]
    reruns = [
        make_row(0, is_clf="True", performance=0.55),
        make_row(1, is_clf="True", performance=0.58),
        make_row(2, is_clf="False", performance=22),
        make_row(3, is_clf="False", performance=29),
        make_row(4, is_clf="False", performance=41),
    ]
    result = run_report(tmp_path, originals, reruns)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "out"
    classification = summary_row(out, "performance", "classification")
    regression = summary_row(out, "performance", "regression")
    assert classification["n_pairs"] == "2"
    assert regression["n_pairs"] == "3"
    assert float(regression["cv_mean"]) == pytest.approx(
        plain_expected([20, 30, 40], [22, 29, 41])["cv_mean"]
    )
    assert summary_row(out, "total_time_s")["n_pairs"] == "5"
    performance_rows = [
        row
        for row in read_rows(out / "noise_summary.csv")
        if row["target"] == "performance"
    ]
    assert len(performance_rows) == 2


def test_is_classification_accepts_numeric_flags(tmp_path):
    originals = [
        make_row(0, is_clf="1", performance=0.5),
        make_row(1, is_clf="0", performance=9),
    ]
    reruns = [
        make_row(0, is_clf="1", performance=0.6),
        make_row(1, is_clf="0", performance=8),
    ]
    result = run_report(tmp_path, originals, reruns)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "out"
    assert summary_row(out, "performance", "classification")["n_pairs"] == "1"
    assert summary_row(out, "performance", "regression")["n_pairs"] == "1"


@pytest.mark.parametrize("which", ["original", "rerun"])
def test_duplicate_key_exits_nonzero(tmp_path, which):
    rows = [make_row(0, total_time_s=10), make_row(0, total_time_s=11)]
    single = [make_row(0, total_time_s=10)]
    original, rerun = (rows, single) if which == "original" else (single, rows)
    result = run_report(tmp_path, original, rerun)
    assert result.returncode != 0
    assert "duplicate" in result.stderr.lower()


def test_repeat_two_rows_are_ignored(tmp_path):
    originals = [make_row(0, total_time_s=10), make_row(0, repeat=2, total_time_s=99)]
    reruns = [make_row(0, total_time_s=12), make_row(0, repeat=2, total_time_s=98)]
    result = run_report(tmp_path, originals, reruns)
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    assert row["n_pairs"] == "1"
    assert float(row["cv_mean"]) == pytest.approx(abs(2) / math.sqrt(2) / 11)


@pytest.mark.parametrize("bad", ["", "nan", "inf", "-inf"])
def test_non_finite_cell_excludes_that_target_only(tmp_path, bad):
    originals = [
        make_row(0, total_time_s=10, n_epochs=5),
        make_row(1, total_time_s=20, n_epochs=6),
    ]
    reruns = [
        make_row(0, total_time_s=bad, n_epochs=5),
        make_row(1, total_time_s=22, n_epochs=7),
    ]
    result = run_report(tmp_path, originals, reruns)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "out"
    broken = summary_row(out, "total_time_s")
    assert broken["n_pairs"] == "1"
    assert broken["n_excluded"] == "1"
    intact = summary_row(out, "n_epochs")
    assert intact["n_pairs"] == "2"
    assert intact["n_excluded"] == "0"


def test_aggregates_match_plain_python_definitions(tmp_path):
    originals, reruns = [10, 20, 30, 40], [12, 18, 33, 36]
    result = run_report(tmp_path, *time_rows(originals, reruns))
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    expected = plain_expected(originals, reruns)
    assert row["n_pairs"] == "4"
    for name in ("cv_median", "cv_mean", "cv_pooled", "r2_raw", "r2_log1p"):
        assert float(row[name]) == pytest.approx(expected[name]), name


def test_aggregates_with_one_negative_value(tmp_path):
    originals, reruns = [10, 20, 30, -40], [12, 18, 33, 36]
    result = run_report(tmp_path, *time_rows(originals, reruns))
    assert result.returncode == 0, result.stderr
    row = summary_row(tmp_path / "out", "total_time_s")
    expected = plain_expected(originals, reruns)
    assert expected["r2_log1p"] == "NA"
    assert row["r2_log1p"] == "NA"
    for name in ("cv_median", "cv_mean", "cv_pooled", "r2_raw"):
        assert float(row[name]) == pytest.approx(expected[name]), name


def test_pairs_file_holds_values_and_pair_cv(tmp_path):
    result = run_report(tmp_path, *time_rows([10], [12]))
    assert result.returncode == 0, result.stderr
    pairs = [
        row
        for row in read_rows(tmp_path / "out" / "noise_pairs.csv")
        if row["target"] == "total_time_s"
    ]
    assert len(pairs) == 1
    pair = pairs[0]
    assert (pair["strategy"], pair["dataset"], pair["fl_algo"]) == (
        "iid",
        "ds0",
        "CentralizedSync",
    )
    assert float(pair["original"]) == 10
    assert float(pair["rerun"]) == 12
    assert float(pair["pair_cv"]) == pytest.approx(abs(2) / math.sqrt(2) / 11)
    assert pair["reason"] == "included"


def test_every_report_target_is_covered(tmp_path):
    from noise_report import TARGETS as REPORT_TARGETS

    assert REPORT_TARGETS == TARGETS
    originals, reruns, expected = [], [], {}
    for index in range(3):
        original_values, rerun_values = {}, {}
        for target_index, target in enumerate(TARGETS):
            base = 10 * (target_index + 1)
            original_values[target] = base + (1, 3, 7)[index]
            rerun_values[target] = base + (2, 4, 9)[index]
            expected[(target, f"ds{index}")] = (
                original_values[target],
                rerun_values[target],
            )
        originals.append(make_row(index, is_clf="True", **original_values))
        reruns.append(make_row(index, is_clf="True", **rerun_values))

    result = run_report(tmp_path, originals, reruns)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "out"
    summary = read_rows(out / "noise_summary.csv")
    assert {row["target"] for row in summary} == set(REPORT_TARGETS)
    for target in TARGETS:
        row = summary_row(
            out, target, "classification" if target == "performance" else "all"
        )
        assert row["n_pairs"] == "3"
        target_values = [expected[(target, f"ds{i}")] for i in range(3)]
        cvs = [
            abs(original - rerun) / math.sqrt(2) / abs((original + rerun) / 2)
            for original, rerun in target_values
        ]
        assert float(row["cv_median"]) == pytest.approx(statistics.median(cvs))
        truth = [original for original, _ in target_values]
        pred = [rerun for _, rerun in target_values]
        mean = sum(truth) / len(truth)
        expected_r2 = 1 - sum((a - b) ** 2 for a, b in zip(truth, pred)) / sum(
            (a - mean) ** 2 for a in truth
        )
        assert float(row["r2_raw"]) == pytest.approx(expected_r2)
        pairs = [
            pair
            for pair in read_rows(out / "noise_pairs.csv")
            if pair["target"] == target
        ]
        assert len(pairs) == 3
        for pair in pairs:
            original, rerun = expected[(target, pair["dataset"])]
            assert float(pair["original"]) == pytest.approx(original)
            assert float(pair["rerun"]) == pytest.approx(rerun)


def test_writes_only_the_two_output_files(tmp_path):
    result = run_report(tmp_path, *time_rows([10, 20], [12, 18]))
    assert result.returncode == 0, result.stderr
    names = sorted(path.name for path in (tmp_path / "out").iterdir())
    assert names == ["noise_pairs.csv", "noise_summary.csv"]


def test_refuses_out_dir_holding_setup_marker(tmp_path):
    out = tmp_path / "campaign"
    out.mkdir()
    (out / ".setup_complete").write_text("")
    result = run_report(tmp_path, *time_rows([10, 20], [12, 18]), out_dir=out)
    assert result.returncode != 0
    assert ".setup_complete" in result.stderr
    assert not (out / "noise_summary.csv").exists()
    assert not (out / "noise_pairs.csv").exists()


def test_refuses_out_dir_below_setup_marker(tmp_path):
    root = tmp_path / "campaign"
    root.mkdir()
    (root / ".setup_complete").write_text("")
    out = root / "nested" / "report"
    result = run_report(tmp_path, *time_rows([10, 20], [12, 18]), out_dir=out)
    assert result.returncode != 0
    assert not out.exists()
