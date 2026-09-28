from datetime import datetime

import pytest

from flexfl.builtins.Results import Results
from run_logs import write_run_logs


def test_get_work_times(tmp_path):
    r = Results(str(write_run_logs(tmp_path / "run")))
    df = r.get_work_times().reset_index(drop=True)
    assert list(df.columns) == ["nid", "lid", "start", "end", "duration"]
    expected = [
        (1, 1, 100.75, 102.75, 2.0),
        (1, 1, 111.0, 113.0, 2.0),
        (2, 3, 99.5, 101.5, 2.0),
        (2, 4, 105.25, 108.25, 3.0),
    ]
    for row, (nid, lid, start, end, duration) in zip(df.itertuples(index=False), expected, strict=True):
        assert (row.nid, row.lid) == (nid, lid)
        assert row.start == datetime.fromtimestamp(start)
        assert row.end == datetime.fromtimestamp(end)
        assert row.duration == pytest.approx(duration)


def test_get_comms(tmp_path, capsys):
    r = Results(str(write_run_logs(tmp_path / "run")))
    df = r.get_comms().reset_index(drop=True)
    assert list(df.columns) == [
        "send_nid", "send_lid", "recv_nid", "recv_lid", "start", "end",
        "duration (ms)", "payload_size (bytes)",
    ]
    expected = [
        (0, 0, 1, 1, 100.25, 100.5, 250.0, 10),
        (0, 0, 2, 3, 100.25, 99.5, 0.0, 10),
        (1, 1, 0, 0, 103.0, 103.5, 500.0, 20),
        (2, 3, 0, 0, 103.5, 104.0, 500.0, 20),
        (0, 0, 2, 4, 105.0, 105.25, 250.0, 10),
        (2, 4, 0, 0, 108.5, 109.0, 500.0, 20),
    ]
    for row, values in zip(df.itertuples(index=False, name=None), expected, strict=True):
        assert row[:4] == values[:4]
        assert row[4] == datetime.fromtimestamp(values[4])
        assert row[5] == datetime.fromtimestamp(values[5])
        assert row[6] == pytest.approx(values[6])
        assert row[7] == values[7]
    assert "clamped 1 negative comm durations to 0 (max skew 750.0 ms; likely clock skew); 0 send/recv pairs unmatched." in capsys.readouterr().out


def test_get_work_time_per_worker(tmp_path):
    r = Results(str(write_run_logs(tmp_path / "run")))
    records = r.get_work_time_per_worker().reset_index(drop=True).to_dict("records")
    assert records == [
        {"worker": 1, "work_time (s)": pytest.approx(4.0)},
        {"worker": 2, "work_time (s)": pytest.approx(5.0)},
    ]


def test_get_comms_per_worker(tmp_path):
    r = Results(str(write_run_logs(tmp_path / "run")))
    df = r.get_comms_per_worker().reset_index(drop=True)
    assert list(df.columns) == ["worker", "comm_time (s)", "payload_size (MB)", "n_messages"]
    assert list(df["worker"]) == [1, 2]
    assert list(df["comm_time (s)"]) == pytest.approx([0.75, 1.25])
    assert list(df["payload_size (MB)"]) == pytest.approx([30 / 1024 / 1024, 60 / 1024 / 1024])
    assert list(df["n_messages"]) == [2, 4]


def test_get_serialization_per_worker(tmp_path):
    r = Results(str(write_run_logs(tmp_path / "run")))
    records = r.get_serialization_per_worker().reset_index(drop=True).to_dict("records")
    assert records == [
        {"worker": 1, "serial_time (s)": pytest.approx(0.5)},
        {"worker": 2, "serial_time (s)": pytest.approx(0.0)},
    ]


def test_get_worker_time_status(tmp_path):
    r = Results(str(write_run_logs(tmp_path / "run")))
    df = r.get_worker_time_status().reset_index(drop=True)
    assert list(df.columns) == [
        "worker", "comm_time (s)", "payload_size (MB)", "n_messages", "work_time (s)",
        "total_time (s)", "serial_time (s)", "other_time (s)", "comm_time% (s)",
        "work_time% (s)", "serial_time% (s)", "other_time% (s)",
    ]
    expected = [
        (1, 0.75, 30 / 1024 / 1024, 2, 4.0, 12.5, 0.5, 7.25, 6.0, 32.0, 4.0, 58.0),
        (2, 1.25, 60 / 1024 / 1024, 4, 5.0, 9.0, 0.0, 2.75, 13.888889, 55.555556, 0.0, 30.555556),
    ]
    for row, values in zip(df.itertuples(index=False, name=None), expected, strict=True):
        assert row[0] == values[0]
        assert row[3] == values[3]
        for i in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11):
            assert row[i] == pytest.approx(values[i], rel=1e-6)


def test_saved_csvs(tmp_path):
    run = write_run_logs(tmp_path / "run")
    r = Results(str(run))
    r.save_results(r.getp_worker_time, r.get_overall_status)
    assert (run / "_analysis" / "worker_time.csv").read_text() == (
        "Worker,Total transfered (MB),Total Messages,Communication Time (s),Communication Time (%),Work Time (s),Work Time (%),Serialization Time (s),Serialization Time (%),Other Time (s),Other Time (%)\n"
        "1,2.86102294921875e-05,2,0.75,6.0,4.0,32.0,0.5,4.0,7.25,57.99999999999999\n"
        "2,5.7220458984375e-05,4,1.25,13.88888888888889,5.0,55.55555555555556,0.0,0.0,2.75,30.555555555555557\n"
    )
    assert (run / "_analysis" / "overall_status.csv").read_text() == (
        "Worker,Idle without fail,Worked successfully<br>without failing,Failed while idle,Failed while working,Failed after<br>working successfully,Non Critical Failures,Total Failures,Working times\n"
        "worker_1,0,1,0,0,0,0,0,1\n"
        "worker_2,0,1,0,0,0,0,0,1\n"
        "All,0,2,0,0,0,0,0,2\n"
    )


def test_get_comms_missing_master(tmp_path):
    run = write_run_logs(tmp_path / "nomaster")
    (run / "log_0.jsonl").unlink()
    r = Results(str(run))
    with pytest.raises(AssertionError, match=r"^Log 0 not found in results folder\.$"):
        r.get_comms()
