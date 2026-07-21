import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "send_dataset.sh"

COPY_TO_VM_DOUBLE = '''
copy_to_vm() {
    local dest="$VMHOME/${3#\\~/}"
    mkdir -p "$(dirname "$dest")"
    cp "$2" "$dest"
}
'''

COPY_TO_VM_FAILING_DOUBLE = '''
copy_to_vm() {
    return 1
}
'''


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
