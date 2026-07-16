#!/usr/bin/env python3
"""Resolve the ip <-> (node, vmid) mapping from ids.json and ips.json.

ids.json and ips.json are written by pxm-tools' Proxmox.start_all_vms in the
same per-node order, positionally aligned within each node. This module joins
them into a flat, ordered list of {"ip", "node", "vmid"} rows (anchor node
first, matching subset_ids.py's convention), for use as the join key between
run participants (workers.txt) and per-host benchmark files.

Depends on pxm-tools >= 0.1.5, which writes both files with this schema: a
top-level object keyed by node name, each value being {"api": str, "ids": list}
in ids.json and {"api": str, "ips": list} in ips.json. Within each node the
i-th entry of "ips" is the IP of the i-th vmid in "ids"; that positional
alignment is the load_mapping join contract. pxm-tools guards it on the
producer side in tests/test_proxmox.py (TestStartAllVmsPositionalAlignment);
tests/test_vm_identity.py pins the consumer side here.
"""
import argparse
import json
import sys
from pathlib import Path


def load_mapping(ids_path: Path, ips_path: Path) -> tuple[list[dict], list[str]]:
    ids = json.loads(Path(ids_path).read_text())
    ips = json.loads(Path(ips_path).read_text())

    ids_nodes = set(ids.keys())
    ips_nodes = set(ips.keys())
    if ids_nodes != ips_nodes:
        only_ids = sorted(ids_nodes - ips_nodes)
        only_ips = sorted(ips_nodes - ids_nodes)
        raise ValueError(
            f"node mismatch between ids and ips files: only in ids={only_ids}, only in ips={only_ips}"
        )

    rows = []
    for node in ids:
        node_ids = ids[node]["ids"]
        node_ips = ips[node]["ips"]
        if len(node_ids) != len(node_ips):
            raise ValueError(
                f"node '{node}': ids has {len(node_ids)} entries but ips has {len(node_ips)}"
            )
        for vmid, ip in zip(node_ids, node_ips):
            rows.append({"ip": ip, "node": node, "vmid": vmid})

    warnings = []
    seen_by_ip = {}
    for row in rows:
        pair = (row["node"], row["vmid"])
        if row["ip"] in seen_by_ip and seen_by_ip[row["ip"]] != pair:
            warnings.append(
                f"duplicate ip {row['ip']} shared by {seen_by_ip[row['ip']]} and {pair}"
            )
        else:
            seen_by_ip[row["ip"]] = pair

    return rows, warnings


def main():
    p = argparse.ArgumentParser(description="Resolve the ip <-> (node, vmid) mapping.")
    p.add_argument("--ids", type=Path, required=True)
    p.add_argument("--ips", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None, help="Write here; otherwise print to stdout")
    args = p.parse_args()

    try:
        rows, warnings = load_mapping(args.ids, args.ips)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    for w in warnings:
        print(f"  ! {w}", file=sys.stderr)

    text = "\n".join(f"{r['ip']} {r['node']} {r['vmid']}" for r in rows)
    if text:
        text += "\n"

    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
