import json
import os
import shutil
import subprocess
from pathlib import Path

from sample_hyperparameters import sample

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "_sweep_common.sh"


def _run(snippet, cwd=None, env=None):
    script = f"source '{SCRIPT}'\n{snippet}"
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=cwd or SCRIPT.parents[1],
        env=env,
    )


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


COMBO = "atnog-test1_2_hobbit_2_samwise_2"
DATA = "clf_cat_compas-two-years"
ALGO = "CentralizedSync"
SEEDS = (42, 43, 44)


def _hp(seed, tmp_path, algo=ALGO):
    out = tmp_path / f"hp_{seed}.json"
    result = _run(f'sample_hp_args {COMBO} {DATA} {algo} {seed} "{out}"')
    assert result.returncode == 0, result.stderr
    return result.stdout.strip(), json.loads(out.read_text())


def test_seeds_get_different_hyperparameters(tmp_path):
    lines = {_hp(seed, tmp_path)[0] for seed in SEEDS}

    assert len(lines) == 3


def test_helper_key_is_combo_dataset_algo_seed(tmp_path):
    line, written = _hp(42, tmp_path)

    assert written == sample(ALGO, f"{COMBO}|{DATA}|{ALGO}|42")
    assert written != sample(ALGO, f"{COMBO}|{DATA}|{ALGO}")
    assert line.startswith("--learning_rate 0.000155 --batch_size 1024 ")


def test_same_seed_reproduces_the_vector(tmp_path):
    assert _hp(43, tmp_path) == _hp(43, tmp_path)


def _stub_sweep_workdir(tmp_path):
    work = tmp_path / "work"
    scripts = work / "scripts"
    bin_dir = tmp_path / "bin"
    scripts.mkdir(parents=True)
    bin_dir.mkdir()
    shutil.copy(SCRIPT.parent / "sample_hyperparameters.py", scripts)
    for name in ("subset_ids.py", "vm_identity.py", "compute_partition_entropy.py"):
        (scripts / name).write_text("")
    for name in ("dataset_division.sh", "send_dataset.sh", "run_commands.sh"):
        (scripts / name).write_text("exit 0\n")
    (scripts / "gather_results.sh").write_text(
        'while getopts "f:o:" o; do [ "$o" = o ] && out="$OPTARG"; done\n'
        'mkdir -p "$out/master"\n'
        '{ for i in 1 2 3 4 5 6; do echo \'{"event": "new_worker"}\'; done\n'
        '  echo \'{"event": "end"}\'; } > "$out/master/log_0.jsonl"\n'
    )
    uv = bin_dir / "uv"
    uv.write_text("#!/bin/bash\nexit 0\n")
    uv.chmod(0o755)
    return work, bin_dir


def test_each_repeat_runs_with_its_own_vector_and_records_it(tmp_path):
    work, bin_dir = _stub_sweep_workdir(tmp_path)
    calls = tmp_path / "calls.txt"
    snippet = f"""
distributions=(iid); atnog_test1=(2); hobbit=(2); samwise=(2)
datasets=({DATA}); fl_algos=({ALGO}); REPEATS=3; SEEDS=(42 43 44)
IDS_FILE=ids.json; IDS_SUBSET=ids_subset.json; IPS_SUBSET=ips_subset.json
IPS_SUBSET_TXT=ips_subset.txt; RESULTS_ROOT=results; PXM_DIR=.
FAIL_LOG=results/_failures.log; EXTRA_ARGS=()
mkdir -p results
execute_fl_run() {{ echo "$4|$5" >> "{calls}"; run_rc=0; }}
run_sweep
"""
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}

    result = _run(snippet, cwd=work, env=env)

    assert result.returncode == 0, result.stderr
    expected = {seed: sample(ALGO, f"{COMBO}|{DATA}|{ALGO}|{seed}") for seed in SEEDS}
    ran = dict(line.split("|", 1) for line in calls.read_text().splitlines())
    for seed, params in expected.items():
        assert ran[str(seed)] == " ".join(f"--{k} {v}" for k, v in params.items())
        rep = (
            work / "results/iid" / COMBO / DATA / ALGO / f"rep_{SEEDS.index(seed) + 1}"
        )
        assert json.loads((rep / "hyperparameters.json").read_text()) == params
        assert (rep / "_SUCCESS").exists()
