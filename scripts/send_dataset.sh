#!/bin/bash

export $(grep -v '^#' .env | xargs)

USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"

usage() {
    echo "Usage: $0 -d <dataset> [-f <ips_file>]" >&2
    echo "Example: $0 -d clf_num_bank-marketing -f scripts/ips.txt" >&2
}

DATASET=""
VM_LIST="scripts/ips.txt"

while getopts ":d:f:" opt; do
    case "$opt" in
        d) DATASET="$OPTARG" ;;
        f) VM_LIST="$OPTARG" ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$DATASET" ]]; then
    usage
    exit 1
fi

if [ ! -d "data/$DATASET" ]; then
    echo "Error: Dataset folder 'data/$DATASET' not found!"
    exit 1
fi

if [ ! -f "$VM_LIST" ]; then
    echo "Error: VM list file '$VM_LIST' not found!"
    exit 1
fi

CONFIG_SRC="results/hyperparameter_optimization/$DATASET.json"

function send_dataset {
    local IP=$1
    local NODE_ID=$2

    echo "Sending dataset $DATASET/node_$NODE_ID to $IP..."
    sshpass -p "$PASSWORD" ssh -n $ARGS "$USERNAME@$IP" "mkdir -p ~/flexfl/data/$DATASET" > /dev/null 2>&1 &&
    sshpass -p "$PASSWORD" scp $ARGS -r "data/$DATASET/node_$NODE_ID" "$USERNAME@$IP:~/flexfl/data/$DATASET" > /dev/null 2>&1 &&
    sshpass -p "$PASSWORD" ssh -n $ARGS "$USERNAME@$IP" "mv ~/flexfl/data/$DATASET/node_$NODE_ID ~/flexfl/data/$DATASET/my_data" > /dev/null 2>&1
    local rc=$?

    if [ -f "$CONFIG_SRC" ]; then
        sshpass -p "$PASSWORD" scp $ARGS "$CONFIG_SRC" "$USERNAME@$IP:~/flexfl/data/$DATASET/$DATASET.json" > /dev/null 2>&1
    else
        echo "Warning: no HPO config at $CONFIG_SRC; --nn benchmark will fail on $IP for $DATASET" >&2
    fi

    if [ $rc -eq 0 ]; then
        echo "Dataset sent to $IP successfully!"
    else
        echo "Failed to send dataset to $IP!"
    fi
}

NODE_ID=0
while read -r IP; do
    if [[ -z "$IP" || "$IP" =~ ^# ]]; then
        continue
    fi
    send_dataset "$IP" "$NODE_ID" &
    NODE_ID=$((NODE_ID + 1))
done < "$VM_LIST"
wait
echo "Dataset setup completed!"
