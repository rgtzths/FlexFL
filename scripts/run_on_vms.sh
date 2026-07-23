#!/bin/bash

export $(grep -v '^#' .env | xargs)

USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-n -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"

usage() {
    echo "Usage: $0 [-f <ips_file>] <interval> <chance> [run_args...]" >&2
    echo "Example: $0 -f scripts/ips.txt 60 0.1 --dataset Benchmark" >&2
}

VM_LIST="scripts/ips.txt"

while getopts ":f:" opt; do
    case "$opt" in
        f) VM_LIST="$OPTARG" ;;
        *)
            usage
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

INTERVAL=$1
CHANCE=$2
shift 2
RUN_ARGS=$@

if ! [[ "$INTERVAL" =~ ^[0-9]+(\.[0-9]+)?$ && "$CHANCE" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "Error: Interval and chance must be float numbers."
    exit 1
fi

if [ ! -f "$VM_LIST" ]; then
    echo "Error: VM list file '$VM_LIST' not found!"
    exit 1
fi

echo "Killing all sessions..."
bash scripts/run_commands.sh -i "$VM_LIST" "pkill -f flexfl 2>/dev/null; screen -wipe >/dev/null 2>&1 || true" > /dev/null 2>&1

# Clear any prior run's results so the completion check below cannot match a stale
# log_0.jsonl from an earlier run (e.g. a master that died before writing its own log).
bash scripts/run_commands.sh -i "$VM_LIST" "rm -rf ~/flexfl/results" > /dev/null 2>&1

read -r MASTER_IP < "$VM_LIST"

function run_command {
    local IP=$1
    local WORKER_ID=$2
    echo "Running command on $IP..."
    COMMAND="cd flexfl && source venv/bin/activate && flexfl-res -s $WORKER_ID -i $INTERVAL -c $CHANCE -w 10 flexfl --results_folder worker_$WORKER_ID --ip \"$MASTER_IP\" --data_folder my_data $RUN_ARGS"
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "screen -dmS fl-worker-$WORKER_ID bash -c \"$COMMAND\""
}

echo "Running command on master..."
INFO="interval_{$INTERVAL}_chance_{$CHANCE}"
COMMAND="cd flexfl && source venv/bin/activate && flexfl --is_anchor --data_folder my_data --info $INFO $RUN_ARGS"
sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$MASTER_IP" "screen -dmS fl-master bash -c \"$COMMAND\""

echo "Waiting..."
sleep 5

WORKER_ID=1
while read -r IP_; do
    if [[ -z "$IP_" || "$IP_" =~ ^# ]]; then
        continue
    fi
    run_command "$IP_" "$WORKER_ID" &
    WORKER_ID=$((WORKER_ID + 1))
done < <(tail -n +2 "$VM_LIST")
wait
echo "Command execution completed!"


# Stall watchdog: poll the master's log_0.jsonl mtime+size instead of blocking on a
# single unbounded remote wait. Every SEND/RECV/JOIN/LEAVE/EPOCH event the FL loop
# performs writes a new line to the master's own log in real time (see FederatedABC /
# WorkerManager / the comm backends), so a run that keeps producing them is never
# killed regardless of total wall-clock; a run whose log stops advancing for
# STALL_TIMEOUT is killed. STALL_BACKSTOP is a generous absolute bound purely to catch
# a pathological case.
STALL_TIMEOUT="${FLEXFL_STALL_TIMEOUT:-1200}"
STALL_BACKSTOP="${FLEXFL_STALL_BACKSTOP:-21600}"
POLL_INTERVAL=30
SSH_CHECK_ARGS="$ARGS -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3"

echo "Waiting for master to finish (stall timeout ${STALL_TIMEOUT}s, backstop ${STALL_BACKSTOP}s)..."
start_ts=$(date +%s)
last_progress_ts=$start_ts
last_log_state=""
stalled=0

export SSHPASS="$PASSWORD"
while true; do
    # Capture $? from the command itself, NOT from `if ! CMD; then` — inside that
    # then-branch, $? reflects the negated condition the `if` already resolved
    # (always 0), not CMD's real exit code, which would make the "screen ended
    # cleanly" branch below unreachable and kill every run, including successful
    # ones, once STALL_TIMEOUT elapses after completion.
    sshpass -e ssh $SSH_CHECK_ARGS "$USERNAME@$MASTER_IP" \
        "screen -list | grep -q fl-master" 2>/dev/null
    ssh_rc=$?
    if [ "$ssh_rc" -ne 0 ]; then
        if [ "$ssh_rc" -eq 1 ]; then
            break  # grep found no match over a successful ssh connection: screen ended
        fi
        # ssh itself failed (e.g. a transient VPN blip) — don't conclude the run
        # ended; retry on the next poll instead of false-failing a healthy run.
        echo "  (transient SSH check failure, rc=$ssh_rc — retrying)" >&2
    fi

    log_state=$(sshpass -e ssh $SSH_CHECK_ARGS "$USERNAME@$MASTER_IP" \
        "find ~/flexfl/results -name 'log_0.jsonl' -printf '%T@ %s\n' 2>/dev/null | head -n 1")
    now=$(date +%s)
    if [ -n "$log_state" ] && [ "$log_state" != "$last_log_state" ]; then
        last_log_state="$log_state"
        last_progress_ts=$now
    fi

    if (( now - last_progress_ts >= STALL_TIMEOUT )); then
        echo "FAILURE: master log made no progress for ${STALL_TIMEOUT}s — stalled, killing run." >&2
        stalled=1
        break
    fi
    if (( now - start_ts >= STALL_BACKSTOP )); then
        echo "FAILURE: run exceeded the ${STALL_BACKSTOP}s absolute backstop — killing run." >&2
        stalled=1
        break
    fi

    sleep "$POLL_INTERVAL"
done
unset SSHPASS

if [ "$stalled" -eq 1 ]; then
    bash scripts/run_commands.sh -i "$VM_LIST" "pkill -f flexfl 2>/dev/null; screen -wipe >/dev/null 2>&1 || true"
    exit 1
fi

# A clean master run logs a terminal 'end' event as the last thing it does.
# A crash exits without it; a SIGTERM kill exits 0 (handler calls sys.exit(0))
# but also without it. So the presence of that event is the only reliable
# success signal, and it is what distinguishes a finished run from a corrupt one.
echo "Checking master run completion..."
MASTER_LOG=$(sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$MASTER_IP" \
    "find ~/flexfl/results -name 'log_0.jsonl' 2>/dev/null | head -n 1")

if [ -z "$MASTER_LOG" ]; then
    echo "FAILURE: master produced no log_0.jsonl — the run did not start or died immediately."
    exit 1
fi

if sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$MASTER_IP" \
    "grep -q '\"event\": \"end\"' '$MASTER_LOG'"; then
    echo "Done! Master run completed cleanly."
    exit 0
fi

echo "FAILURE: master log has no terminal 'end' event — the run crashed or was killed."
exit 1
