import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gather_results.sh"

STUB_SSHPASS = """\
#!/bin/bash
echo "$*" >> "$SSH_LOG"
for arg in "$@"; do
    case "$arg" in
        *@*:*) ip="${arg#*@}"; ip="${ip%%:*}";;
    esac
done
for bad in ${FAIL_IPS:-}; do
    [ "$ip" = "$bad" ] && exit 1
done
if [ "$ip" = "${HOLD_IP:-}" ]; then
    while [ ! -e "$RELEASE" ]; do sleep 0.05; done
fi
mkdir -p "${@: -1}"
echo "log from $ip" > "${@: -1}/log_$ip.jsonl"
"""

IPS = ("10.0.0.1", "10.0.0.2", "10.0.0.3")


def _prepare(tmp_path, *, fail_ips=(), hold_ip=""):
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
    release = tmp_path / "release"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SSH_LOG": str(ssh_log),
        "FAIL_IPS": " ".join(fail_ips),
        "HOLD_IP": hold_ip,
        "RELEASE": str(release),
    }
    return work, env, ssh_log, release


COMMAND = ["bash", "scripts/gather_results.sh", "-f", "ips.txt", "-o", "out"]


def _gather(tmp_path, *, fail_ips=()):
    work, env, ssh_log, _ = _prepare(tmp_path, fail_ips=fail_ips)
    proc = subprocess.run(COMMAND, cwd=work, env=env, capture_output=True, text=True)
    return work / "out", ssh_log.read_text().splitlines(), proc


def test_all_copies_succeeding_exits_zero(tmp_path):
    out, ssh_calls, proc = _gather(tmp_path)

    assert proc.returncode == 0, proc.stderr
    assert "Results copying completed!" in proc.stdout
    assert sorted(p.name for p in out.iterdir()) == [f"log_{ip}.jsonl" for ip in IPS]
    assert len(ssh_calls) == len(IPS)


@pytest.mark.parametrize("fail_ip", IPS)
def test_one_failed_copy_exits_nonzero_after_the_others_finish(tmp_path, fail_ip):
    out, _, proc = _gather(tmp_path, fail_ips=(fail_ip,))

    assert proc.returncode == 1
    assert f"Failed to copy results from {fail_ip}!" in proc.stdout
    assert f"Results copying failed for 1 VM(s): {fail_ip}" in proc.stderr
    assert "Results copying completed!" not in proc.stdout
    assert sorted(p.name for p in out.iterdir()) == [
        f"log_{ip}.jsonl" for ip in IPS if ip != fail_ip
    ]


def test_every_failed_copy_is_named(tmp_path):
    out, _, proc = _gather(tmp_path, fail_ips=("10.0.0.1", "10.0.0.3"))

    assert proc.returncode == 1
    assert "Results copying failed for 2 VM(s): 10.0.0.1 10.0.0.3" in proc.stderr
    assert [p.name for p in out.iterdir()] == ["log_10.0.0.2.jsonl"]


def test_failed_copy_touches_no_remote_state(tmp_path):
    _, ssh_calls, proc = _gather(tmp_path, fail_ips=("10.0.0.2",))

    assert proc.returncode == 1
    assert len(ssh_calls) == len(IPS)
    assert all(" scp " in f" {call} " for call in ssh_calls)
    assert not any("rm " in call for call in ssh_calls)


def test_gather_does_not_exit_while_another_copy_is_still_running(tmp_path):
    work, env, ssh_log, release = _prepare(
        tmp_path, fail_ips=("10.0.0.1",), hold_ip="10.0.0.3"
    )
    out_file = tmp_path / "stdout.txt"
    err_file = tmp_path / "stderr.txt"
    with open(out_file, "w") as out, open(err_file, "w") as err:
        proc = subprocess.Popen(COMMAND, cwd=work, env=env, stdout=out, stderr=err)
        try:
            deadline = time.monotonic() + 10
            while len(ssh_log.read_text().splitlines()) < len(IPS):
                assert time.monotonic() < deadline, "copies did not start"
                time.sleep(0.05)
            time.sleep(0.5)

            assert proc.poll() is None

            release.touch()
            assert proc.wait(timeout=10) == 1
        finally:
            release.touch()
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    assert sorted(p.name for p in (work / "out").iterdir()) == [
        "log_10.0.0.2.jsonl",
        "log_10.0.0.3.jsonl",
    ]
    assert "Results copying failed for 1 VM(s): 10.0.0.1" in err_file.read_text()
