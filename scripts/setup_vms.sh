#!/bin/bash

export $(grep -v '^#' .env | xargs)

KEY_NAME="id_rsa"
KEY_PATH="keys/$KEY_NAME"
USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
export SSHPASS="$PASSWORD"
VM_LIST="scripts/ips.txt"
FLEXFL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IPS_JSON=""
CONCURRENCY="${FLEXFL_SETUP_CONCURRENCY:-8}"

usage() {
    echo "Usage: $0 [-f <ips_file>] [-j <ips_json>]" >&2
    echo "Example: $0 -f scripts/ips_all.txt -j scripts/ips_all.json" >&2
    echo "  -j orders the workers round-robin across Proxmox nodes" >&2
    echo "  FLEXFL_SETUP_CONCURRENCY caps simultaneous workers (default 8)" >&2
    echo "Requires: sshpass on the control host" >&2
}

while getopts ":f:j:" opt; do
    case "$opt" in
        f) VM_LIST="$OPTARG" ;;
        j) IPS_JSON="$OPTARG" ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if [ ! -f "$VM_LIST" ]; then
    echo "Error: VM list file '$VM_LIST' not found!"
    exit 1
fi

if [ ! -f "$KEY_PATH" ]; then
    echo "Generating SSH key..."
    mkdir -p keys
    ssh-keygen -t rsa -b 4096 -f "$KEY_PATH" -N "" > /dev/null 2>&1
    echo "SSH key generated at $KEY_PATH"
fi

if ! command -v sshpass >/dev/null 2>&1; then
    echo "Error: sshpass not found on this control host." >&2
    echo "Install it and re-run, e.g.:" >&2
    echo "  Debian/Ubuntu: sudo apt install -y sshpass" >&2
    echo "  Arch/CachyOS:  sudo pacman -S sshpass" >&2
    echo "  Fedora:        sudo dnf install -y sshpass" >&2
    echo "  macOS:         brew install sshpass" >&2
    exit 1
fi

function setup_worker {
    local IP=$1
    echo "Setting up $IP..."
    sshpass -p "$PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -f -i "$KEY_PATH.pub" "$USERNAME@$IP" > /dev/null 2>&1 &&
    sshpass -p "$PASSWORD" scp $ARGS "$KEY_PATH" "$USERNAME@$IP:~/.ssh/" &&
    sshpass -p "$PASSWORD" scp $ARGS "$KEY_PATH.pub" "$USERNAME@$IP:~/.ssh/" &&
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "chmod 600 ~/.ssh/$KEY_NAME && touch ~/.ssh/known_hosts && mkdir -p ~/scripts" &&
    sshpass -p "$PASSWORD" scp $ARGS "$VM_LIST" "$USERNAME@$IP:~/scripts/ips.txt" &&
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "mkdir -p ~/flexfl" &&
    rsync -az --exclude='data/' --exclude='results/' --exclude='.venv/' \
        --rsh='sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q' \
        "$FLEXFL_DIR/" "$USERNAME@$IP:~/flexfl/" &&
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "bash ~/flexfl/scripts/vm.sh"
    if [ $? -eq 0 ]; then
        echo "Setup completed successfully on $IP."
    else
        echo "Error: Setup failed on $IP."
    fi
}

# Emits the VMs of $VM_LIST round-robin across the nodes of $IPS_JSON.
# IPs absent from the json keep their original relative position, at the end.
interleave_by_node() {
    python3 - "$VM_LIST" "$IPS_JSON" <<'PYEOF'
import json, sys
from itertools import zip_longest

with open(sys.argv[1]) as f:
    wanted = [l.strip() for l in f if l.strip() and not l.startswith("#")]
with open(sys.argv[2]) as f:
    by_node = json.load(f)

order, seen = [], set()
per_node = []
for node in by_node:
    ips = [ip for ip in by_node[node].get("ips", []) if ip in wanted]
    if ips:
        per_node.append(ips)
for group in zip_longest(*per_node):
    for ip in group:
        if ip is not None and ip not in seen:
            seen.add(ip)
            order.append(ip)
order += [ip for ip in wanted if ip not in seen]
print("\n".join(order))
PYEOF
}

if [ -n "$IPS_JSON" ] && [ -f "$IPS_JSON" ]; then
    mapfile -t WORKLIST < <(interleave_by_node)
    echo "Ordering ${#WORKLIST[@]} VMs round-robin across nodes from $IPS_JSON"
else
    mapfile -t WORKLIST < <(grep -vE '^[[:space:]]*(#|$)' "$VM_LIST")
fi

echo "Setting up ${#WORKLIST[@]} VMs, at most $CONCURRENCY at a time..."
for IP_ in "${WORKLIST[@]}"; do
    setup_worker "$IP_" &
    while [ "$(jobs -rp | wc -l)" -ge "$CONCURRENCY" ]; do
        wait -n
    done
done
wait

echo "SSH setup completed!"
