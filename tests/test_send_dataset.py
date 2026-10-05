import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "send_dataset.sh"

COPY_TO_VM_DOUBLE = """
copy_to_vm() {
    local dest="$VMHOME/${3#\\~/}"
    mkdir -p "$(dirname "$dest")"
    cp "$2" "$dest"
}
"""

COPY_TO_VM_FAILING_DOUBLE = """
copy_to_vm() {
    return 1
}
"""


def _run(snippet, vmhome):
    script = f"VMHOME='{vmhome}'\nsource '{SCRIPT}'\n{snippet}"
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
    )


def test_ship_config_lands_under_data(tmp_path):
    vmhome = tmp_path / "vmhome"
    config_src = tmp_path / "dummy.json"
    config_src.write_text('{"n_layers": 1}')

    snippet = f"""
{COPY_TO_VM_DOUBLE}
ship_config "user@host" "dummy" "{config_src}"
echo "RC=$?"
"""
    result = _run(snippet, vmhome)

    assert "RC=0" in result.stdout
    dest = vmhome / "flexfl" / "data" / "dummy" / "dummy.json"
    assert dest.exists()
    assert dest.read_text() == '{"n_layers": 1}'
    assert not (vmhome / "flexfl" / "results").exists()


def test_ship_config_absent_warns_not_fails(tmp_path):
    vmhome = tmp_path / "vmhome"
    config_src = tmp_path / "does_not_exist.json"

    snippet = f"""
{COPY_TO_VM_DOUBLE}
ship_config "user@host" "dummy" "{config_src}"
echo "RC=$?"
"""
    result = _run(snippet, vmhome)

    assert "RC=0" in result.stdout
    assert "no HPO config" in result.stderr
    assert not (vmhome / "flexfl" / "data" / "dummy" / "dummy.json").exists()


def test_ship_config_present_transfer_failure_errors(tmp_path):
    vmhome = tmp_path / "vmhome"
    config_src = tmp_path / "dummy.json"
    config_src.write_text('{"n_layers": 1}')

    snippet = f"""
{COPY_TO_VM_FAILING_DOUBLE}
ship_config "user@host" "dummy" "{config_src}"
echo "RC=$?"
"""
    result = _run(snippet, vmhome)

    assert "RC=1" in result.stdout
    assert "Failed to send HPO config" in result.stderr


VM_DOUBLES = """
copy_to_vm() {
    local dest="$VMHOME/${1#*@}/${3#\\~/}"
    mkdir -p "$(dirname "$dest")"
    cp "$2" "$dest"
}
copy_dir_to_vm() {
    cp -R "$2" "$VMHOME/${1#*@}/${3#\\~/}/"
}
run_on_vm() {
    mkdir -p "$VMHOME/${1#*@}"
    HOME="$VMHOME/${1#*@}" bash -c "$2"
}
"""

GLOBALS = """
USERNAME=user
DATASET=ds
CONFIG_SRC=config.json
"""

TRAIN = {"x_train.npy": b"fresh-x", "y_train.npy": b"fresh-y"}
VAL = {"x_val.npy": b"val-x", "y_val.npy": b"val-y"}


def _run_in(snippet, vmhome, cwd):
    script = f"VMHOME='{vmhome}'\nsource '{SCRIPT}'\n{VM_DOUBLES}\n{GLOBALS}\n{snippet}"
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, cwd=cwd
    )


def _local_partition(cwd, node_id, files):
    node = cwd / "data" / "ds" / f"node_{node_id}"
    node.mkdir(parents=True)
    for name, content in files.items():
        (node / name).write_bytes(content)
    return node


def _vm_data(vmhome, host="host"):
    return vmhome / host / "flexfl" / "data" / "ds"


def test_send_dataset_replaces_stale_my_data(tmp_path):
    vmhome = tmp_path / "vmhome"
    _local_partition(tmp_path, 1, TRAIN)
    (tmp_path / "config.json").write_text("{}")
    stale = _vm_data(vmhome) / "my_data"
    stale.mkdir(parents=True)
    (stale / "x_train.npy").write_bytes(b"stale-x")
    (stale / "y_train.npy").write_bytes(b"stale-y")
    leftover = _vm_data(vmhome) / "node_1"
    leftover.mkdir()
    (leftover / "junk.npy").write_bytes(b"junk")

    result = _run_in('send_dataset host 1; echo "RC=$?"', vmhome, tmp_path)

    assert "RC=0" in result.stdout, result.stderr
    my_data = _vm_data(vmhome) / "my_data"
    assert (my_data / "x_train.npy").read_bytes() == b"fresh-x"
    assert (my_data / "y_train.npy").read_bytes() == b"fresh-y"
    assert sorted(p.name for p in my_data.iterdir()) == ["x_train.npy", "y_train.npy"]
    assert not (_vm_data(vmhome) / "node_1").exists()
    assert (_vm_data(vmhome) / "ds.json").exists()


def test_send_dataset_ships_validation_pair_to_node_0(tmp_path):
    vmhome = tmp_path / "vmhome"
    _local_partition(tmp_path, 0, VAL)

    result = _run_in('send_dataset host 0; echo "RC=$?"', vmhome, tmp_path)

    assert "RC=0" in result.stdout, result.stderr
    my_data = _vm_data(vmhome) / "my_data"
    assert (my_data / "x_val.npy").read_bytes() == b"val-x"
    assert (my_data / "y_val.npy").read_bytes() == b"val-y"


@pytest.mark.parametrize(
    "tamper",
    [
        'printf stale > "$landed/x_train.npy"',
        'printf stale > "$landed/y_train.npy"',
        'rm "$landed/y_train.npy"',
        'printf extra > "$landed/z_extra.npy"',
    ],
)
def test_send_dataset_rejects_partition_that_differs_on_the_vm(tmp_path, tamper):
    vmhome = tmp_path / "vmhome"
    _local_partition(tmp_path, 1, TRAIN)
    tampering_copy = f"""
copy_dir_to_vm() {{
    local dest="$VMHOME/${{1#*@}}/${{3#\\~/}}"
    cp -R "$2" "$dest/"
    local landed="$dest/$(basename "$2")"
    {tamper}
}}
"""

    result = _run_in(
        tampering_copy + 'send_dataset host 1; echo "RC=$?"', vmhome, tmp_path
    )

    assert "RC=1" in result.stdout
    assert "checksum mismatch" in result.stderr
    assert "successfully" not in result.stdout


@pytest.mark.parametrize(
    "node_id,files,missing",
    [
        (1, TRAIN, "x_train.npy"),
        (1, TRAIN, "y_train.npy"),
        (0, VAL, "x_val.npy"),
        (0, VAL, "y_val.npy"),
    ],
)
def test_send_dataset_missing_local_file_leaves_vm_untouched(
    tmp_path, node_id, files, missing
):
    vmhome = tmp_path / "vmhome"
    _local_partition(
        tmp_path, node_id, {k: v for k, v in files.items() if k != missing}
    )
    existing = _vm_data(vmhome) / "my_data"
    existing.mkdir(parents=True)
    (existing / "old.npy").write_bytes(b"old")

    result = _run_in(f'send_dataset host {node_id}; echo "RC=$?"', vmhome, tmp_path)

    assert "RC=1" in result.stdout
    assert f"missing local data/ds/node_{node_id}/{missing}" in result.stderr
    assert (existing / "old.npy").read_bytes() == b"old"


def _regression_cache(cwd):
    cache = cwd / "data" / "ds" / "_data"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "scaling.json").write_text(
        '{\n    "target": {\n        "mean": 1.0\n    }\n}'
    )


@pytest.mark.parametrize("node_id,files", [(1, TRAIN), (0, VAL)])
def test_send_dataset_requires_target_file_for_regression(tmp_path, node_id, files):
    vmhome = tmp_path / "vmhome"
    _local_partition(tmp_path, node_id, files)
    _regression_cache(tmp_path)

    result = _run_in(f'send_dataset host {node_id}; echo "RC=$?"', vmhome, tmp_path)

    assert "RC=1" in result.stdout
    missing = f"missing local data/ds/node_{node_id}/target_scaling.json"
    assert missing in result.stderr
    assert not vmhome.exists()


def test_send_dataset_ships_target_file_for_regression(tmp_path):
    vmhome = tmp_path / "vmhome"
    _local_partition(tmp_path, 1, {**TRAIN, "target_scaling.json": b"{}"})
    _regression_cache(tmp_path)

    result = _run_in('send_dataset host 1; echo "RC=$?"', vmhome, tmp_path)

    assert "RC=0" in result.stdout, result.stderr
    assert (_vm_data(vmhome) / "my_data" / "target_scaling.json").read_bytes() == b"{}"


STAGE_FAILURES = {
    "local hash": ("local_npy_manifest() { return 1; }", "cannot hash local"),
    "cleanup": (
        'run_on_vm() { case "$2" in rm*) return 1 ;; esac; _real_run_on_vm "$@"; }',
        "remote cleanup failed",
    ),
    "copy": ("copy_dir_to_vm() { return 1; }", "copy failed"),
    "rename": (
        'run_on_vm() { case "$2" in mv*) return 1 ;; esac; _real_run_on_vm "$@"; }',
        "rename to my_data failed",
    ),
    "remote hash": (
        'run_on_vm() { case "$2" in cd*) return 1 ;; esac; _real_run_on_vm "$@"; }',
        "cannot hash remote my_data",
    ),
    "config": ("copy_to_vm() { return 1; }", "HPO config transfer FAILED"),
}


@pytest.mark.parametrize("stage", list(STAGE_FAILURES))
def test_send_dataset_fails_at_each_stage(tmp_path, stage):
    vmhome = tmp_path / "vmhome"
    _local_partition(tmp_path, 1, TRAIN)
    (tmp_path / "config.json").write_text("{}")
    override, message = STAGE_FAILURES[stage]
    keep_real = 'eval "_real_run_on_vm() $(declare -f run_on_vm | tail -n +2)"'

    result = _run_in(
        f'{keep_real}\n{override}\nsend_dataset host 1; echo "RC=$?"', vmhome, tmp_path
    )

    assert "RC=1" in result.stdout
    assert message in result.stderr
    assert "successfully" not in result.stdout


def test_transport_wrappers_pass_recursive_copy_and_detached_ssh(tmp_path):
    arglog = tmp_path / "args.log"
    snippet = f"""
PASSWORD=pw
ARGS="-o X=1 -q"
sshpass() {{ printf '%s|' "$@" >> '{arglog}'; printf '\\n' >> '{arglog}'; echo remote-out; }}
copy_dir_to_vm user@host data/ds/node_1 "~/flexfl/data/ds"
echo "COPY=$?"
out="$(run_on_vm user@host "cd ~/x && ls")"
echo "RUN=$? OUT=$out"
"""
    result = subprocess.run(
        ["bash", "-c", f"source '{SCRIPT}'\n{snippet}"], capture_output=True, text=True
    )

    assert "COPY=0" in result.stdout
    assert "RUN=0 OUT=remote-out" in result.stdout
    scp_call, ssh_call = arglog.read_text().splitlines()
    assert (
        scp_call == "-p|pw|scp|-o|X=1|-q|-r|data/ds/node_1|user@host:~/flexfl/data/ds|"
    )
    assert ssh_call == "-p|pw|ssh|-n|-o|X=1|-q|user@host|cd ~/x && ls|"


def _main_setup(tmp_path, ips_text):
    (tmp_path / ".env").write_text("VM_USERNAME=user\nVM_PASSWORD=pw\n")
    (tmp_path / "ips.txt").write_text(ips_text)
    _local_partition(tmp_path, 0, VAL)
    _local_partition(tmp_path, 1, TRAIN)


@pytest.mark.parametrize(
    "failing,count",
    [
        ("10.0.0.1", 1),
        ("10.0.0.2", 1),
        ("10.0.0.*", 2),
    ],
)
def test_main_exits_nonzero_when_any_vm_fails(tmp_path, failing, count):
    vmhome = tmp_path / "vmhome"
    _main_setup(tmp_path, "10.0.0.1\n10.0.0.2\n")
    failing_copy = f"""
copy_dir_to_vm() {{
    case "$1" in *@{failing}) return 1 ;; esac
    cp -R "$2" "$VMHOME/${{1#*@}}/${{3#\\~/}}/"
}}
"""

    result = _run_in(failing_copy + "main -d ds -f ips.txt", vmhome, tmp_path)

    assert result.returncode == 1
    assert f"FAILED on {count} VM(s)" in result.stderr
    assert "Dataset setup completed!" not in result.stdout


def test_main_sends_each_partition_to_its_vm(tmp_path):
    vmhome = tmp_path / "vmhome"
    _main_setup(tmp_path, "10.0.0.1\n10.0.0.2\n")

    result = _run_in("main -d ds -f ips.txt", vmhome, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Dataset setup completed!" in result.stdout
    assert (
        _vm_data(vmhome, "10.0.0.1") / "my_data" / "x_val.npy"
    ).read_bytes() == b"val-x"
    assert (
        _vm_data(vmhome, "10.0.0.2") / "my_data" / "x_train.npy"
    ).read_bytes() == b"fresh-x"


@pytest.mark.parametrize("ips_text", ["", "# only a comment\n\n"])
def test_main_rejects_a_list_without_vms(tmp_path, ips_text):
    vmhome = tmp_path / "vmhome"
    _main_setup(tmp_path, ips_text)

    result = _run_in("main -d ds -f ips.txt", vmhome, tmp_path)

    assert result.returncode == 1
    assert "no VMs listed" in result.stderr
    assert "Dataset setup completed!" not in result.stdout


def test_main_rejects_unsafe_dataset_name_before_touching_vms(tmp_path):
    vmhome = tmp_path / "vmhome"
    _main_setup(tmp_path, "10.0.0.1\n")
    (tmp_path / "data" / "ds x").mkdir()

    result = _run_in('main -d "ds x" -f ips.txt', vmhome, tmp_path)

    assert result.returncode == 1
    assert "invalid dataset name" in result.stderr
    assert not vmhome.exists()


def test_run_on_vm_double_expands_only_unquoted_tilde(tmp_path):
    vmhome = tmp_path / "vmhome"
    result = _run_in("run_on_vm user@host 'echo ~/a \"~/b\"'", vmhome, tmp_path)

    assert result.stdout.strip() == f"{vmhome}/host/a ~/b"
