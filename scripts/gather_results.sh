#!/bin/bash

export $(grep -v '^#' .env | xargs)

USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"

usage() {
    echo "Usage: $0 [-f <ips_file>] [-o <output_dir>]" >&2
    echo "Example: $0 -f scripts/ips.txt -o results/2_4_8/clf_num_bank-marketing/CentralizedSync" >&2
}

VM_LIST="scripts/ips.txt"
OUTPUT_DIR="."

while getopts ":f:o:" opt; do
    case "$opt" in
        f) VM_LIST="$OPTARG" ;;
        o) OUTPUT_DIR="$OPTARG" ;;
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

mkdir -p "$OUTPUT_DIR"

function copy_results {
    local IP=$1
    echo "Copying results from $IP..."
    sshpass -p "$PASSWORD" scp $ARGS -r "$USERNAME@$IP:~/flexfl/results/." "$OUTPUT_DIR/"
    if [ $? -eq 0 ]; then
        echo "Results copied from $IP successfully!"
    else
        echo "Failed to copy results from $IP!"
    fi
}

while read -r IP; do
    if [[ -z "$IP" || "$IP" =~ ^# ]]; then
        continue
    fi
    copy_results "$IP" &
done < "$VM_LIST"
wait
echo "Results copying completed!"
