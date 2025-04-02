#!/bin/bash

WORKERS=$1
INTERVAL=$2
CHANCE=$3
shift 3
RUN_ARGS=$@

echo "Running command locally with and $WORKERS workers, interval $INTERVAL and chance $CHANCE, do you want to continue? (y/n)"
read -r CONTINUE
if [[ "$CONTINUE" != "y" ]]; then
    echo "Exiting..."
    exit 1
fi

echo "Running master..."
COMMAND="uv run flexfl --is_anchor --no-save_model $RUN_ARGS"
screen -dmS fl-master bash -c "$COMMAND"

echo "Waiting..."
sleep 10

function run_command {
    local WORKER_ID=$1
    echo "Running worker $WORKER_ID..."
    COMMAND="uv run flexfl-res -s $WORKER_ID -i $INTERVAL -c $CHANCE flexfl --subfolder worker_$WORKER_ID  $RUN_ARGS"
    screen -dmS fl-worker-$WORKER_ID bash -c "$COMMAND"
}

for (( WORKER_ID=1; WORKER_ID<=$WORKERS; WORKER_ID++ )); do
    run_command "$WORKER_ID" &
done
wait
echo "Command execution completed!"

# pkill screen