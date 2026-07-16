#!/bin/bash

export $(grep -v '^#' .env | xargs)

IDS_JSON="${1:-scripts/ids.json}"
IPS_JSON="${2:-scripts/ips.json}"
OUTPUT_DIR="${3:-results}"
shift 3

USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
SSH_ARGS="-n -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
SCP_ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
BENCH_ARGS="$@"

if [ ! -f "$IDS_JSON" ]; then
    echo "Error: ids file '$IDS_JSON' not found!"
    exit 1
fi

if [ ! -f "$IPS_JSON" ]; then
    echo "Error: ips file '$IPS_JSON' not found!"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

if ! ROWS="$(python3 scripts/vm_identity.py --ids "$IDS_JSON" --ips "$IPS_JSON")"; then
    echo "Error: vm_identity.py failed" >&2; exit 1
fi
[ -n "$ROWS" ] || { echo "Error: empty VM mapping" >&2; exit 1; }

function run_benchmark {
    local IP=$1
    local NODE=$2
    local VMID=$3
    local REMOTE_RESULT="machine_benchmark_${NODE}_${VMID}.json"

    echo "[$IP] Running benchmark..."
    sshpass -p "$PASSWORD" ssh $SSH_ARGS "$USERNAME@$IP" \
        "cd flexfl && source venv/bin/activate && python src/other/machine_benchmark.py --output ~/$REMOTE_RESULT $BENCH_ARGS"

    echo "[$IP] Fetching results..."
    sshpass -p "$PASSWORD" scp $SCP_ARGS "$USERNAME@$IP:$REMOTE_RESULT" "$OUTPUT_DIR/machine_benchmark_${NODE}_${VMID}.json"

    sshpass -p "$PASSWORD" ssh $SSH_ARGS "$USERNAME@$IP" "rm -f ~/$REMOTE_RESULT"

    echo "[$IP] Done -> results/machine_benchmark_${NODE}_${VMID}.json"
}

while read -r IP NODE VMID; do
    [[ -z "$IP" || "$IP" =~ ^# ]] && continue
    run_benchmark "$IP" "$NODE" "$VMID" &
done <<< "$ROWS"

wait
collected=$(find "$OUTPUT_DIR" -maxdepth 1 -name 'machine_benchmark_*.json' -type f | wc -l)
if [ "$collected" -eq 0 ]; then
    echo "Error: zero benchmark files collected — every remote benchmark failed" >&2
    exit 1
fi
echo "All benchmarks completed! ($collected files)"
