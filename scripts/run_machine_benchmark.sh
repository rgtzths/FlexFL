#!/bin/bash

export $(grep -v '^#' .env | xargs)

VM_LIST="${1:-scripts/ips.txt}"
OUTPUT_DIR="${2:-results}"
shift 2

USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
SSH_ARGS="-n -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
SCP_ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
BENCH_ARGS="$@"

if [ ! -f "$VM_LIST" ]; then
    echo "Error: VM list file '$VM_LIST' not found!"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

function run_benchmark {
    local IP=$1
    local REMOTE_RESULT="machine_benchmark_${IP}.json"

    echo "[$IP] Running benchmark..."
    sshpass -p "$PASSWORD" ssh $SSH_ARGS "$USERNAME@$IP" \
        "cd flexfl && source venv/bin/activate && python src/other/machine_benchmark.py --output ~/$REMOTE_RESULT $BENCH_ARGS"

    echo "[$IP] Fetching results..."
    sshpass -p "$PASSWORD" scp $SCP_ARGS "$USERNAME@$IP:$REMOTE_RESULT" "$OUTPUT_DIR/machine_benchmark_${IP}.json"

    sshpass -p "$PASSWORD" ssh $SSH_ARGS "$USERNAME@$IP" "rm -f ~/$REMOTE_RESULT"

    echo "[$IP] Done -> results/machine_benchmark_${IP}.json"
}

while read -r IP; do
    [[ -z "$IP" || "$IP" =~ ^# ]] && continue
    run_benchmark "$IP" &
done < "$VM_LIST"

wait
echo "All benchmarks completed!"
