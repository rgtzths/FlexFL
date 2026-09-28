import subprocess
import sys
from pathlib import Path

import pytest

from flexfl.builtins.event_metrics import decomposition
from run_logs import golden_logs


def test_golden_decomposition():
    result = decomposition(*golden_logs(), 100.0, 110.0)
    assert result == {
        "compute_time_total_s": pytest.approx(6.5),
        "compute_time_max_s": pytest.approx(4.5),
        "comm_time_total_s": pytest.approx(2.0),
        "comm_time_max_s": pytest.approx(1.25),
        "serial_time_total_s": pytest.approx(1.0),
        "validation_time_s": pytest.approx(1.0),
        "comm_skew_clamped": 1,
        "n_work_intervals_in_window": 3,
        "n_work_events_in_window": 5,
        "n_unmatched_comms": 0,
        "n_orphan_comms": 0,
        "n_unclosed_work_logs": 0,
        "n_unmatched_validations": 0,
    }


def test_unclipped_work():
    result = decomposition(*golden_logs(), 0.0, 1000.0)
    assert result["compute_time_total_s"] == pytest.approx(9.0)
    assert result["compute_time_max_s"] == pytest.approx(5.0)


def test_failure_terminated_work():
    logs = {0: [], 7: [{"event": "working_start", "timestamp": 101.0}, {"event": "failure", "timestamp": 103.0}]}
    result = decomposition(logs, {0: 0, 7: 1}, 100.0, 110.0)
    assert result["compute_time_total_s"] == pytest.approx(2.0)
    assert result["n_unclosed_work_logs"] == 0


def test_unpaired_work():
    logs = {0: [], 7: [
        {"event": "working_start", "timestamp": 101.0},
        {"event": "working_end", "timestamp": 102.0},
        {"event": "working_start", "timestamp": 104.0},
    ]}
    result = decomposition(logs, {0: 0, 7: 1}, 100.0, 110.0)
    assert result["compute_time_total_s"] == pytest.approx(1.0)
    assert result["n_unclosed_work_logs"] == 1


def test_unmatched_message():
    logs, log2node = golden_logs()
    logs[4] = [e for e in logs[4] if e["event"] != "send"]
    result = decomposition(logs, log2node, 100.0, 110.0)
    assert result["n_unmatched_comms"] == 1
    assert result["comm_time_total_s"] == pytest.approx(1.5)
    assert result["comm_time_max_s"] == pytest.approx(0.75)


def test_serialization_straddles_window():
    logs = {
        0: [{"event": "encode", "time": 0.3, "timestamp": 100.1}],
        7: [{"event": "working_start", "timestamp": 101.0}, {"event": "working_end", "timestamp": 102.0}],
    }
    result = decomposition(logs, {0: 0, 7: 1}, 100.0, 110.0)
    assert result["serial_time_total_s"] == pytest.approx(0.1)


def test_comm_and_validation_clip_both_edges():
    result = decomposition(*golden_logs(), 100.4, 104.5)
    assert result["compute_time_total_s"] == pytest.approx(3.1)
    assert result["compute_time_max_s"] == pytest.approx(2.0)
    assert result["comm_time_total_s"] == pytest.approx(1.1)
    assert result["comm_time_max_s"] == pytest.approx(0.6)
    assert result["serial_time_total_s"] == pytest.approx(0.75)
    assert result["validation_time_s"] == pytest.approx(0.5)


def test_orphan_messages():
    logs, log2node = golden_logs()
    del logs[4]
    del log2node[4]
    result = decomposition(logs, log2node, 100.0, 110.0)
    assert result["n_orphan_comms"] == 2
    assert result["compute_time_total_s"] == pytest.approx(3.5)


def test_unpaired_validation():
    logs, log2node = golden_logs()
    logs[0].insert(-1, {"event": "validation_start", "timestamp": 105.5})
    result = decomposition(logs, log2node, 100.0, 110.0)
    assert result["n_unmatched_validations"] == 1


def test_work_event_without_interval():
    logs = {0: [], 7: [{"event": "working_start", "timestamp": 105.0}]}
    result = decomposition(logs, {0: 0, 7: 1}, 100.0, 110.0)
    assert result["n_work_intervals_in_window"] == 0
    assert result["n_work_events_in_window"] == 1


def test_event_metrics_import_is_stdlib_only():
    src = Path(__file__).resolve().parent.parent / "src"
    result = subprocess.run([
        sys.executable, "-c",
        "import sys; sys.path.insert(0, sys.argv[1]); import flexfl.builtins.event_metrics; assert 'pandas' not in sys.modules and 'numpy' not in sys.modules",
        str(src),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
