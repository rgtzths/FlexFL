import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "_sweep_common.sh"


def _run(snippet):
    script = f"source '{SCRIPT}'\n{snippet}"
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def _make_run_dir(tmp_path, *, end=True, new_workers=0):
    """Gathered-output layout: the master log sits nested under the run dir."""
    log_dir = tmp_path / "rep_1" / "master" / "2026-08-26_10:00:00"
    log_dir.mkdir(parents=True)
    lines = [
        json.dumps({"event": "new_worker", "timestamp": 1.0, "node_id": i, "info": {}})
        for i in range(1, new_workers + 1)
    ]
    lines.append(json.dumps({"event": "start", "timestamp": 2.0}))
    if end:
        lines.append(json.dumps({"event": "end", "timestamp": 3.0}))
    (log_dir / "log_0.jsonl").write_text("\n".join(lines) + "\n")
    return tmp_path / "rep_1"


def test_full_participation_passes(tmp_path):
    run_dir = _make_run_dir(tmp_path, end=True, new_workers=4)

    result = _run(f'run_output_complete "{run_dir}" 4; echo "RC=$?"')

    assert "RC=0" in result.stdout


def test_short_pool_is_rejected(tmp_path):
    run_dir = _make_run_dir(tmp_path, end=True, new_workers=3)

    result = _run(f'run_output_complete "{run_dir}" 4; echo "RC=$?"')

    assert "RC=1" in result.stdout


def test_missing_end_event_is_rejected(tmp_path):
    run_dir = _make_run_dir(tmp_path, end=False, new_workers=4)

    result = _run(f'run_output_complete "{run_dir}" 4; echo "RC=$?"')

    assert "RC=1" in result.stdout


def test_expected_omitted_skips_participation_check(tmp_path):
    run_dir = _make_run_dir(tmp_path, end=True, new_workers=0)

    result = _run(f'run_output_complete "{run_dir}"; echo "RC=$?"')

    assert "RC=0" in result.stdout


def test_rejoin_above_expected_still_passes(tmp_path):
    run_dir = _make_run_dir(tmp_path, end=True, new_workers=5)

    result = _run(f'run_output_complete "{run_dir}" 4; echo "RC=$?"')

    assert "RC=0" in result.stdout


def test_missing_log_is_rejected(tmp_path):
    empty = tmp_path / "rep_1"
    empty.mkdir()

    result = _run(f'run_output_complete "{empty}" 4; echo "RC=$?"')

    assert "RC=1" in result.stdout
