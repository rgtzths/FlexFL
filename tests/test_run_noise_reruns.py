import json
import os
import re
import shutil
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

import pytest
from sample_hyperparameters import sample

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
RERUN = SCRIPTS / "run_noise_reruns.sh"
COMMON = SCRIPTS / "_sweep_common.sh"
FULL = SCRIPTS / "run_full_experiments.sh"

STRATEGY = "iid"
TOTAL = 6
COMBO = "atnog-test1_2_hobbit_2_samwise_2"
DATA_A = "clf_num_a"
DATA_B = "clf_num_b"
SYNC = "CentralizedSync"
DSYNC = "DecentralizedSync"
FIXED_ENTROPY = {"mean": 0.25, "max": 0.5}

Run = namedtuple("Run", "work root calls sampled proc")

STUB_ENTROPY = """\
import argparse
import json

p = argparse.ArgumentParser()
p.add_argument("--data-dir")
p.add_argument("--num-workers")
p.add_argument("--update-json")
a = p.parse_args()
d = json.load(open(a.update_json))
d["worker_feature_entropy"] = {"mean": 0.25, "max": 0.5}
json.dump(d, open(a.update_json, "w"))
"""

STUB_RECORD_PY = """\
import os
import sys

open(os.environ["CALLS"], "a").write(
    os.path.basename(sys.argv[0]) + " " + " ".join(sys.argv[1:]) + "\\n"
)
"""

STUB_DIVISION = """\
while getopts "d:n:s:p:" o; do
    case "$o" in
        d) d="$OPTARG";;
        n) n="$OPTARG";;
        s) s="$OPTARG";;
        p) p="$OPTARG";;
    esac
done
echo "dataset_division -d $d -n $n -s $s -p $p" >> "$CALLS"
mkdir -p "data/$d/node_0"
[ "$d" = "${FAIL_DIVISION_FOR:-}" ] && exit 1
exit 0
"""

STUB_SEND = """\
while getopts "d:f:" o; do
    case "$o" in d) d="$OPTARG";; f) f="$OPTARG";; esac
done
echo "send_dataset -d $d -f $f" >> "$CALLS"
[ "$d" = "${FAIL_SEND_FOR:-}" ] && exit 1
exit 0
"""

STUB_RUN_ON_VMS = """\
echo "run_on_vms $*" >> "$CALLS"
if [ -z "${OMIT_ARGS_JSON:-}" ]; then
    "$REAL_PYTHON" - "$@" <<'PY'
import argparse
import json
import os
import sys

p = argparse.ArgumentParser()
for name in ("dataset", "data_name", "nn", "fl", "info", "early_stop_on"):
    p.add_argument("--" + name)
for name in (
    "seed",
    "min_workers",
    "batch_size",
    "patience",
    "local_epochs",
    "epochs",
    "min_epochs",
):
    p.add_argument("--" + name, type=int)
for name in ("learning_rate", "delta"):
    p.add_argument("--" + name, type=float)
args, _ = p.parse_known_args(sys.argv[1:])
with open(os.environ["CALLS"] + ".args.json", "w") as f:
    json.dump({k: v for k, v in vars(args).items() if v is not None}, f)
PY
fi
if [ -n "${TAMPER_HP:-}" ]; then
    for f in $(find "$FLEXFL_NOISE_ROOT" -name '.hp_*.json'); do
        echo '{"learning_rate": 1}' > "$f"
    done
fi
exit "${RUN_RC:-0}"
"""

STUB_GATHER = """\
while getopts "f:o:" o; do [ "$o" = o ] && out="$OPTARG"; done
mkdir -p "$out/master"
{ for i in 1 2 3 4 5 6; do echo '{"event": "new_worker"}'; done
  echo '{"event": "end"}'; } > "$out/master/log_0.jsonl"
[ ! -f "$CALLS.args.json" ] || cp "$CALLS.args.json" "$out/master/args.json"
for i in 1 2 3 4 5 6; do
    [ "$i" = "${GATHER_SHORT:-}" ] && continue
    mkdir -p "$out/master/worker_$i"
    echo '{"event": "start"}' > "$out/master/worker_$i/log_$i.jsonl"
done
"""

STUB_UV = """\
#!/bin/bash
echo "uv $*" >> "$CALLS"
if [ "${1:-}" = run ] && [ "${2:-}" = python ]; then
    shift 2
    exec python3 "$@"
fi
exit 0
"""

STUB_PYTHON3 = """\
#!/bin/bash
case "$*" in *sample_hyperparameters.py*) echo "$*" >> "$SAMPLED";; esac
exec "$REAL_PYTHON" "$@"
"""

STUB_GROUPS_FAIL = f"""\
import runpy
import sys

if sys.argv[1] == "groups":
    print("stub groups failure", file=sys.stderr)
    sys.exit(1)
runpy.run_path({str(SCRIPTS / "noise_configs.py")!r}, run_name="__main__")
"""


def _executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


def _stub_workdir(tmp_path):
    work = tmp_path / "work"
    scripts = work / "scripts"
    bin_dir = tmp_path / "bin"
    scripts.mkdir(parents=True)
    bin_dir.mkdir()
    for name in (
        "run_noise_reruns.sh",
        "_sweep_common.sh",
        "noise_configs.py",
        "sample_hyperparameters.py",
    ):
        shutil.copy(SCRIPTS / name, scripts / name)
    (scripts / "subset_ids.py").write_text(STUB_RECORD_PY)
    (scripts / "vm_identity.py").write_text(STUB_RECORD_PY)
    (scripts / "compute_partition_entropy.py").write_text(STUB_ENTROPY)
    (scripts / "dataset_division.sh").write_text(STUB_DIVISION)
    (scripts / "send_dataset.sh").write_text(STUB_SEND)
    (scripts / "run_commands.sh").write_text('echo "run_commands $*" >> "$CALLS"\n')
    (scripts / "run_on_vms.sh").write_text(STUB_RUN_ON_VMS)
    (scripts / "gather_results.sh").write_text(STUB_GATHER)
    (scripts / "ids.json").write_text("{}")
    _executable(bin_dir / "uv", STUB_UV)
    _executable(bin_dir / "python3", STUB_PYTHON3)
    (tmp_path / "pxm").mkdir()
    return work, bin_dir


def _division(data):
    return {
        "dataset": data,
        "num_workers": TOTAL,
        "nodes": {"atnog-test1": 2, "hobbit": 2, "samwise": 2},
        "strategy": STRATEGY,
        "val_size": 0,
        "test_size": 0,
        "distribution_percentage": 0.9,
        "alpha": 0.5,
        "seed": 42,
        "split_version": 2,
        "preprocess": {"val_size": 0.2, "test_size": 0.2},
        "worker_feature_entropy": FIXED_ENTROPY,
    }


def _entry(data, algo, entropy=None, hp=None):
    division = _division(data)
    if entropy is not None:
        division["worker_feature_entropy"] = entropy
    if hp is None:
        hp = sample(algo, f"{COMBO}|{data}|{algo}|42")
    return {
        "strategy": STRATEGY,
        "n1": 2,
        "n2": 2,
        "n3": 2,
        "data_name": data,
        "fl_algo": algo,
        "seed": 42,
        "expected_hyperparameters": hp,
        "expected_division": division,
    }


def _run(
    tmp_path, entries, *, env=None, root=None, setup=None, args=(), list_text=None
):
    work, bin_dir = _stub_workdir(tmp_path)
    if setup is not None:
        setup(work)
    list_path = tmp_path / "list.jsonl"
    if list_text is None:
        list_text = "".join(json.dumps(e) + "\n" for e in entries)
    list_path.write_text(list_text)
    calls = tmp_path / "calls.txt"
    sampled = tmp_path / "sampled.txt"
    calls.touch()
    sampled.touch()
    rerun_root = tmp_path / "rerun"
    base_env = {k: v for k, v in os.environ.items() if not k.startswith("FLEXFL_")}
    full_env = {
        **base_env,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CALLS": str(calls),
        "SAMPLED": str(sampled),
        "REAL_PYTHON": sys.executable,
        "FLEXFL_NOISE_LIST": str(list_path),
        "FLEXFL_NOISE_ROOT": str(rerun_root) if root is None else root,
        "FLEXFL_PXM_DIR": str(tmp_path / "pxm"),
        **(env or {}),
    }
    full_env = {k: v for k, v in full_env.items() if v is not None}
    proc = subprocess.run(
        ["bash", "scripts/run_noise_reruns.sh", *args],
        cwd=work,
        env=full_env,
        capture_output=True,
        text=True,
    )
    return Run(work, rerun_root, calls, sampled, proc)


def _calls(run, prefix):
    return [
        line for line in run.calls.read_text().splitlines() if line.startswith(prefix)
    ]


def _rep(run, data, algo):
    return run.root / STRATEGY / COMBO / data / algo / "rep_1"


def _failures(run):
    path = run.root / "_failures.log"
    if not path.exists():
        return []
    return [line.split("  FAILED  ", 1)[1] for line in path.read_text().splitlines()]


def _failure(step, data="", algo=""):
    return f"step={step}  strategy={STRATEGY}  nodes=2_2_2  dataset={data}  fl={algo}"


def _remote_cleanup(run, data):
    ips = run.work / "scripts" / "ips_subset_noise.txt"
    return [
        f"run_commands -i {ips} rm -rf ~/flexfl/data/{data}",
        f"run_commands -i {ips} rm -rf ~/flexfl/results",
    ]


def test_two_entries_rerun_into_the_noise_root_only(tmp_path):
    entries = [_entry(DATA_A, SYNC), _entry(DATA_A, DSYNC)]

    run = _run(tmp_path, entries)

    assert run.proc.returncode == 0, run.proc.stderr
    for algo in (SYNC, DSYNC):
        rep = _rep(run, DATA_A, algo)
        assert (rep / "_SUCCESS").exists()
        assert not (rep / "_FAILED").exists()
        assert json.loads((rep / "hyperparameters.json").read_text()) == sample(
            algo, f"{COMBO}|{DATA_A}|{algo}|42"
        )
    assert not (run.work / "results").exists()
    assert _failures(run) == []
    division = json.loads(
        (run.root / STRATEGY / COMBO / DATA_A / "division.json").read_text()
    )
    assert division == _division(DATA_A)
    assert not list(run.root.rglob(".hp_*"))
    assert not list(run.root.rglob(".expected_*"))
    assert _calls(run, "dataset_division") == [
        f"dataset_division -d {DATA_A} -n {TOTAL} -s {STRATEGY} -p 1"
    ]
    runs = _calls(run, "run_on_vms")
    assert len(runs) == 2
    for line, algo in zip(runs, (SYNC, DSYNC)):
        assert f"--data_name {DATA_A} " in line
        assert f"--fl {algo} --seed 42 --min_workers {TOTAL} " in line
    for line in _remote_cleanup(run, DATA_A):
        assert line in run.calls.read_text().splitlines()
    assert not (run.work / "data" / DATA_A / "node_0").exists()


def test_extra_arguments_reach_the_run(tmp_path):
    run = _run(tmp_path, [_entry(DATA_A, SYNC)], args=("--info", "note"))

    assert run.proc.returncode == 0, run.proc.stderr
    (line,) = _calls(run, "run_on_vms")
    assert line.endswith(" --info note")
    assert (_rep(run, DATA_A, SYNC) / "_SUCCESS").exists()


@pytest.mark.parametrize(
    "args",
    [
        ("--seed", "43"),
        ("--learning_rate", "0.5"),
        ("--epochs", "3"),
        ("--learning_r", "0.5"),
        ("--epochs=3",),
        ("--min_workers", "2"),
        ("--dataset", "Other"),
        ("--nn", "other"),
    ],
)
def test_effective_argument_overrides_fail_the_run(tmp_path, args):
    run = _run(tmp_path, [_entry(DATA_A, SYNC)], args=args)

    assert run.proc.returncode == 0, run.proc.stderr
    rep = _rep(run, DATA_A, SYNC)
    assert not (rep / "_SUCCESS").exists()
    assert (rep / "_FAILED").exists()
    assert _failures(run) == [_failure("args_mismatch", DATA_A, SYNC)]


def test_missing_effective_arguments_fail_the_run(tmp_path):
    run = _run(
        tmp_path,
        [_entry(DATA_A, SYNC)],
        env={"OMIT_ARGS_JSON": "1"},
    )

    assert run.proc.returncode == 0, run.proc.stderr
    assert (_rep(run, DATA_A, SYNC) / "_FAILED").exists()
    assert _failures(run) == [_failure("args_mismatch", DATA_A, SYNC)]


def test_short_gather_fails_the_run(tmp_path):
    run = _run(tmp_path, [_entry(DATA_A, SYNC)], env={"GATHER_SHORT": "3"})

    assert run.proc.returncode == 0, run.proc.stderr
    rep = _rep(run, DATA_A, SYNC)
    assert not (rep / "_SUCCESS").exists()
    assert (rep / "_FAILED").exists()
    assert _failures(run) == [_failure("gather_incomplete", DATA_A, SYNC)]


def test_tampered_expected_hyperparameters_skip_the_entry(tmp_path):
    tampered = dict(sample(SYNC, f"{COMBO}|{DATA_A}|{SYNC}|42"), learning_rate=0.5)
    entries = [_entry(DATA_A, SYNC, hp=tampered), _entry(DATA_A, DSYNC)]

    run = _run(tmp_path, entries)

    assert run.proc.returncode == 0, run.proc.stderr
    assert _failures(run) == [_failure("hp_mismatch", DATA_A, SYNC)]
    assert not _rep(run, DATA_A, SYNC).exists()
    (line,) = _calls(run, "run_on_vms")
    assert f"--fl {DSYNC} " in line
    assert (_rep(run, DATA_A, DSYNC) / "_SUCCESS").exists()
    assert not list(run.root.rglob(".hp_*"))
    assert not list(run.root.rglob(".expected_*"))


def test_differing_entropy_skips_the_dataset_and_cleans_up(tmp_path):
    entries = [
        _entry(DATA_A, SYNC, entropy={"mean": 0.9, "max": 0.5}),
        _entry(DATA_B, SYNC),
    ]

    run = _run(tmp_path, entries)

    assert run.proc.returncode == 0, run.proc.stderr
    assert _failures(run) == [_failure("division_mismatch", DATA_A)]
    assert not _rep(run, DATA_A, SYNC).exists()
    (line,) = _calls(run, "run_on_vms")
    assert f"--data_name {DATA_B} " in line
    assert (_rep(run, DATA_B, SYNC) / "_SUCCESS").exists()
    for data in (DATA_A, DATA_B):
        for cmd in _remote_cleanup(run, data):
            assert cmd in run.calls.read_text().splitlines()
        assert not (run.work / "data" / data / "node_0").exists()
    assert not list(run.root.rglob(".expected_*"))


GUARD_CASES = (
    ("{work}/results", (), "results"),
    ("{work}/results/x/y", (), "results"),
    ("results/sub", (), "results"),
    ("{tmp}/camp", ("{tmp}/camp/.setup_complete",), ".setup_complete"),
    ("{tmp}/camp/a/b", ("{tmp}/camp/.setup_complete",), ".setup_complete"),
    ("{tmp}/camp", ("{tmp}/camp/x/y/.setup_complete",), ".setup_complete"),
)


@pytest.mark.parametrize("root, markers, message", GUARD_CASES)
def test_unsafe_roots_exit_before_any_stub(tmp_path, root, markers, message):
    def setup(work):
        for marker in markers:
            path = Path(marker.format(work=work, tmp=tmp_path))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    run = _run(
        tmp_path,
        [_entry(DATA_A, SYNC)],
        root=root.format(work=tmp_path / "work", tmp=tmp_path),
        setup=setup,
    )

    assert run.proc.returncode == 2
    assert message in run.proc.stderr
    assert run.calls.read_text() == ""
    assert run.sampled.read_text() == ""
    assert not (run.work / "results").exists()
    assert not list(tmp_path.rglob("_failures.log"))


def test_missing_ids_file_exits_before_any_stub(tmp_path):
    missing = tmp_path / "no_ids.json"

    run = _run(
        tmp_path, [_entry(DATA_A, SYNC)], env={"FLEXFL_NOISE_IDS_FILE": str(missing)}
    )

    assert run.proc.returncode == 2
    assert str(missing) in run.proc.stderr
    assert run.calls.read_text() == ""
    assert not run.root.exists()


def test_default_ids_file_must_exist(tmp_path):
    def setup(work):
        (work / "scripts" / "ids.json").unlink()

    run = _run(tmp_path, [_entry(DATA_A, SYNC)], setup=setup)

    assert run.proc.returncode == 2
    assert "ids.json" in run.proc.stderr
    assert run.calls.read_text() == ""


@pytest.mark.parametrize("unset", ("FLEXFL_NOISE_LIST", "FLEXFL_NOISE_ROOT"))
def test_required_variables_must_be_set(tmp_path, unset):
    run = _run(tmp_path, [_entry(DATA_A, SYNC)], env={unset: None})

    assert run.proc.returncode == 2
    assert unset in run.proc.stderr
    assert run.calls.read_text() == ""


def test_list_without_expected_fields_is_rejected(tmp_path):
    entry = _entry(DATA_A, SYNC)
    del entry["expected_division"]

    run = _run(tmp_path, [entry])

    assert run.proc.returncode == 2
    assert "expected_division" in run.proc.stderr
    assert run.calls.read_text() == ""
    assert not run.root.exists()


def test_unavailable_realpath_exits_before_any_stub(tmp_path):
    def setup(work):
        _executable(tmp_path / "bin" / "realpath", "#!/bin/bash\nexit 1\n")

    run = _run(tmp_path, [_entry(DATA_A, SYNC)], setup=setup)

    assert run.proc.returncode == 2
    assert "realpath" in run.proc.stderr
    assert run.calls.read_text() == ""
    assert not run.root.exists()


def test_done_entry_is_skipped_without_sampling(tmp_path):
    entries = [_entry(DATA_A, SYNC), _entry(DATA_A, DSYNC)]

    def setup(work):
        rep = tmp_path / "rerun" / STRATEGY / COMBO / DATA_A / SYNC / "rep_1"
        rep.mkdir(parents=True)
        (rep / "_SUCCESS").touch()

    run = _run(tmp_path, entries, setup=setup)

    assert run.proc.returncode == 0, run.proc.stderr
    (line,) = _calls(run, "run_on_vms")
    assert f"--fl {DSYNC} " in line
    sampled = run.sampled.read_text().splitlines()
    assert len(sampled) == 1
    assert f"{COMBO}|{DATA_A}|{DSYNC}|42" in sampled[0]
    assert not (_rep(run, DATA_A, SYNC) / "hyperparameters.json").exists()
    assert (_rep(run, DATA_A, DSYNC) / "_SUCCESS").exists()


def test_fully_done_dataset_runs_nothing(tmp_path):
    def setup(work):
        rep = tmp_path / "rerun" / STRATEGY / COMBO / DATA_A / SYNC / "rep_1"
        rep.mkdir(parents=True)
        (rep / "_SUCCESS").touch()

    run = _run(tmp_path, [_entry(DATA_A, SYNC)], setup=setup)

    assert run.proc.returncode == 0, run.proc.stderr
    assert f"{COMBO}/{DATA_A}: all algos done, skipping" in run.proc.stdout
    assert _calls(run, "dataset_division") == []
    assert _calls(run, "run_on_vms") == []
    assert run.sampled.read_text() == ""


def _recipe(path):
    match = re.search(
        r'cat > "\$\{base\}/division\.json" <<EOF\n(.*?)\nEOF\n',
        path.read_text(),
        re.S,
    )
    assert match, path
    return " ".join(match.group(1).split())


def _execute_body(path):
    match = re.search(
        r"^execute_fl_run\(\) \{\n(.*?)^\}", path.read_text(), re.S | re.M
    )
    assert match, path
    return " ".join(match.group(1).split())


def test_division_recipe_matches_the_sweep():
    recipe = _recipe(RERUN)

    assert '"split_version": 2' in recipe
    assert recipe == _recipe(COMMON)


def test_execute_fl_run_matches_the_full_launcher():
    body = _execute_body(RERUN)

    assert "run_rc=$?" in body
    assert body == _execute_body(FULL)


def test_written_hyperparameters_mismatch_marks_the_run_failed(tmp_path):
    run = _run(tmp_path, [_entry(DATA_A, SYNC)], env={"TAMPER_HP": "1"})

    assert run.proc.returncode == 0, run.proc.stderr
    rep = _rep(run, DATA_A, SYNC)
    assert (rep / "_FAILED").exists()
    assert not (rep / "_SUCCESS").exists()
    assert _failures(run) == [_failure("hp_written_mismatch", DATA_A, SYNC)]
    assert len(_calls(run, "run_on_vms")) == 1


def test_failed_run_records_no_hyperparameters(tmp_path):
    run = _run(tmp_path, [_entry(DATA_A, SYNC)], env={"RUN_RC": "1"})

    assert run.proc.returncode == 0, run.proc.stderr
    rep = _rep(run, DATA_A, SYNC)
    assert (rep / "_FAILED").exists()
    assert not (rep / "_SUCCESS").exists()
    assert not (rep / "hyperparameters.json").exists()
    assert _failures(run) == [_failure("run_on_vms", DATA_A, SYNC)]
    assert not list(run.root.rglob(".hp_*"))


def test_failing_groups_helper_exits_before_any_vm_stub(tmp_path):
    def setup(work):
        (work / "scripts" / "noise_configs.py").write_text(STUB_GROUPS_FAIL)

    run = _run(tmp_path, [_entry(DATA_A, SYNC)], setup=setup)

    assert run.proc.returncode == 2
    assert "noise_configs.py failed" in run.proc.stderr
    assert run.calls.read_text() == ""


@pytest.mark.parametrize(
    "env, step",
    (
        ({"FAIL_DIVISION_FOR": DATA_A}, "dataset_division"),
        ({"FAIL_SEND_FOR": DATA_A}, "send_dataset"),
    ),
)
def test_failed_division_or_send_still_cleans_up_and_continues(tmp_path, env, step):
    entries = [_entry(DATA_A, SYNC), _entry(DATA_B, SYNC)]

    run = _run(tmp_path, entries, env=env)

    assert run.proc.returncode == 0, run.proc.stderr
    assert _failures(run) == [_failure(step, DATA_A)]
    lines = run.calls.read_text().splitlines()
    for cmd in _remote_cleanup(run, DATA_A):
        assert cmd in lines
    assert not (run.work / "data" / DATA_A / "node_0").exists()
    assert not _rep(run, DATA_A, SYNC).exists()
    (line,) = _calls(run, "run_on_vms")
    assert f"--data_name {DATA_B} " in line
    assert (_rep(run, DATA_B, SYNC) / "_SUCCESS").exists()
