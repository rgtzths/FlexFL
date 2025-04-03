#!/bin/bash

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

VM_LIST="scripts/ips.txt" # needs to end in empty line
USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
INTERVAL=$1
CHANCE=$2
shift 2
RUN_ARGS=$@

echo "Running command on VMs with interval $INTERVAL and chance $CHANCE, do you want to continue? (y/n)"
read -r CONTINUE
if [[ "$CONTINUE" != "y" ]]; then
    echo "Exiting..."
    exit 1
fi

if [ ! -f "$VM_LIST" ]; then
    echo "Error: VM list file '$VM_LIST' not found!"
    exit 1
fi

read -r MASTER_IP < "$VM_LIST"

function run_command {
    local IP=$1
    local WORKER_ID=$2
    echo "Running command on $IP..."
    COMMAND="cd flexfl && source venv/bin/activate && flexfl-res -s $WORKER_ID -i $INTERVAL -c $CHANCE flexfl --results_folder worker_$WORKER_ID --ip \"$MASTER_IP\" $RUN_ARGS"
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "screen -dmS fl-worker-$WORKER_ID bash -c \"$COMMAND\""
}

echo "Running command on master..."
COMMAND="cd flexfl && source venv/bin/activate && flexfl --is_anchor --no-save_model $RUN_ARGS"
sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$MASTER_IP" "screen -dmS fl-master bash -c \"$COMMAND\""

echo "Waiting..."
sleep 10

WORKER_ID=1
while read -r IP; do
    if [[ -z "$IP" || "$IP" =~ ^# ]]; then
        continue
    fi
    run_command "$IP" "$WORKER_ID"
    WORKER_ID=$((WORKER_ID + 1))
    sleep 0.2
done < <(tail -n +2 "$VM_LIST")
wait
echo "Command execution completed!"

# pkill screen