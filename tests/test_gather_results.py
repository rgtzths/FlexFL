import os
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gather_results.sh"

STUB_SSHPASS = """\
#!/bin/bash
echo "$*" >> "$SSH_LOG"
for arg in "$@"; do
    case "$arg" in
        *"@$FAIL_IP:"*) exit 1;;
        *@*:*) ip="${arg#*@}"; ip="${ip%%:*}";;
    esac
done
mkdir -p "${@: -1}"
echo "log from $ip" > "${@: -1}/log_$ip.jsonl"
"""

IPS = ("10.0.0.1", "10.0.0.2", "10.0.0.3")


def _gather(tmp_path, *, fail_ip=""):
    work = tmp_path / "work"
    (work / "scripts").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shutil.copy(SCRIPT, work / "scripts")
    (work / ".env").write_text("VM_USERNAME=user\nVM_PASSWORD=secret\n")
    (work / "ips.txt").write_text("\n".join(IPS) + "\n")
    sshpass = bin_dir / "sshpass"
    sshpass.write_text(STUB_SSHPASS)
    sshpass.chmod(0o755)
    ssh_log = tmp_path / "ssh.txt"
    ssh_log.touch()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SSH_LOG": str(ssh_log),
        "FAIL_IP": fail_ip,
    }
    proc = subprocess.run(
        ["bash", "scripts/gather_results.sh", "-f", "ips.txt", "-o", "out"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    return work / "out", ssh_log.read_text().splitlines(), proc


def test_all_copies_succeeding_exits_zero(tmp_path):
    out, ssh_calls, proc = _gather(tmp_path)

    assert proc.returncode == 0, proc.stderr
    assert "Results copying completed!" in proc.stdout
    assert sorted(p.name for p in out.iterdir()) == [f"log_{ip}.jsonl" for ip in IPS]
    assert len(ssh_calls) == len(IPS)


def test_one_failed_copy_exits_nonzero_after_the_others_finish(tmp_path):
    out, _, proc = _gather(tmp_path, fail_ip="10.0.0.2")

    assert proc.returncode == 1
    assert "Failed to copy results from 10.0.0.2!" in proc.stdout
    assert "Results copying failed for 1 VM(s): 10.0.0.2" in proc.stderr
    assert "Results copying completed!" not in proc.stdout
    assert sorted(p.name for p in out.iterdir()) == [
        "log_10.0.0.1.jsonl",
        "log_10.0.0.3.jsonl",
    ]


def test_failed_copy_touches_no_remote_state(tmp_path):
    _, ssh_calls, proc = _gather(tmp_path, fail_ip="10.0.0.2")

    assert proc.returncode == 1
    assert len(ssh_calls) == len(IPS)
    assert all(" scp " in f" {call} " for call in ssh_calls)
    assert not any("rm " in call for call in ssh_calls)
