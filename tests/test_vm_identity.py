import json
import subprocess
import sys
from pathlib import Path

import pytest

from vm_identity import load_mapping


def write_ids_ips(tmp_path, ids_data, ips_data):
    ids_path = tmp_path / "ids.json"
    ips_path = tmp_path / "ips.json"
    ids_path.write_text(json.dumps(ids_data))
    ips_path.write_text(json.dumps(ips_data))
    return ids_path, ips_path


def test_load_mapping_aligns_positionally_and_preserves_anchor_first(tmp_path):
    ids_data = {
        "frodo": {"api": "https://frodo", "ids": ["104"]},
        "hobbit": {"api": "https://hobbit", "ids": ["108", "109"]},
    }
    ips_data = {
        "frodo": {"api": "https://frodo", "ips": ["10.0.0.1"]},
        "hobbit": {"api": "https://hobbit", "ips": ["10.0.0.2", "10.0.0.3"]},
    }
    ids_path, ips_path = write_ids_ips(tmp_path, ids_data, ips_data)

    rows, warnings = load_mapping(ids_path, ips_path)

    assert warnings == []
    assert rows == [
        {"ip": "10.0.0.1", "node": "frodo", "vmid": "104"},
        {"ip": "10.0.0.2", "node": "hobbit", "vmid": "108"},
        {"ip": "10.0.0.3", "node": "hobbit", "vmid": "109"},
    ]
    assert rows[0]["node"] == "frodo"


def test_load_mapping_raises_on_length_mismatch(tmp_path):
    ids_data = {"hobbit": {"api": "https://hobbit", "ids": ["108", "109"]}}
    ips_data = {"hobbit": {"api": "https://hobbit", "ips": ["10.0.0.2"]}}
    ids_path, ips_path = write_ids_ips(tmp_path, ids_data, ips_data)

    with pytest.raises(ValueError):
        load_mapping(ids_path, ips_path)


def test_load_mapping_raises_on_node_present_in_one_file_only(tmp_path):
    ids_data = {
        "hobbit": {"api": "https://hobbit", "ids": ["108"]},
        "samwise": {"api": "https://samwise", "ids": ["106"]},
    }
    ips_data = {
        "hobbit": {"api": "https://hobbit", "ips": ["10.0.0.2"]},
    }
    ids_path, ips_path = write_ids_ips(tmp_path, ids_data, ips_data)

    with pytest.raises(ValueError):
        load_mapping(ids_path, ips_path)


def test_load_mapping_duplicate_ip_warns_and_does_not_raise(tmp_path):
    ids_data = {
        "hobbit": {"api": "https://hobbit", "ids": ["108"]},
        "samwise": {"api": "https://samwise", "ids": ["106"]},
    }
    ips_data = {
        "hobbit": {"api": "https://hobbit", "ips": ["10.0.0.2"]},
        "samwise": {"api": "https://samwise", "ips": ["10.0.0.2"]},
    }
    ids_path, ips_path = write_ids_ips(tmp_path, ids_data, ips_data)

    rows, warnings = load_mapping(ids_path, ips_path)

    assert len(rows) == 2
    assert len(warnings) == 1
    assert "10.0.0.2" in warnings[0]
    assert "hobbit" in warnings[0] and "108" in warnings[0]
    assert "samwise" in warnings[0] and "106" in warnings[0]


def test_cli_out_writes_ip_node_vmid_lines(tmp_path):
    ids_data = {"hobbit": {"api": "https://hobbit", "ids": ["108", "109"]}}
    ips_data = {"hobbit": {"api": "https://hobbit", "ips": ["10.0.0.2", "10.0.0.3"]}}
    ids_path, ips_path = write_ids_ips(tmp_path, ids_data, ips_data)
    out_path = tmp_path / "workers.txt"

    script = str(Path(__file__).resolve().parent.parent / "scripts" / "vm_identity.py")
    result = subprocess.run(
        [sys.executable, script, "--ids", str(ids_path), "--ips", str(ips_path), "--out", str(out_path)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    lines = out_path.read_text().splitlines()
    assert lines == ["10.0.0.2 hobbit 108", "10.0.0.3 hobbit 109"]


def test_cli_exits_1_on_structural_fault(tmp_path):
    ids_data = {"hobbit": {"api": "https://hobbit", "ids": ["108", "109"]}}
    ips_data = {"hobbit": {"api": "https://hobbit", "ips": ["10.0.0.2"]}}
    ids_path, ips_path = write_ids_ips(tmp_path, ids_data, ips_data)

    script = str(Path(__file__).resolve().parent.parent / "scripts" / "vm_identity.py")
    result = subprocess.run(
        [sys.executable, script, "--ids", str(ids_path), "--ips", str(ips_path)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert result.stderr.strip() != ""
