#!/bin/bash

usage() {
    echo "Usage: $0 -d <dataset> [-f <ips_file>]" >&2
    echo "Example: $0 -d clf_num_bank-marketing -f scripts/ips.txt" >&2
}

# Copy one local file to a VM. Overridable in tests.
# Args: <user@ip> <local_src> <remote_dest>
copy_to_vm() {
    sshpass -p "$PASSWORD" scp $ARGS "$2" "$1:$3" > /dev/null 2>&1
}

# Ship the HPO config to a VM's never-wiped data/ tree.
# Args: <user@ip> <dataset> <config_src>
# Absent config -> warn, return 0 (non-benchmark datasets legitimately have none).
# Present config that fails to transfer -> error, return 1.
ship_config() {
    local target="$1" dataset="$2" config_src="$3"
    if [ ! -f "$config_src" ]; then
        echo "Warning: no HPO config at $config_src; --nn benchmark will fail for $dataset (only needed for --nn benchmark)" >&2
        return 0
    fi
    if ! copy_to_vm "$target" "$config_src" "~/flexfl/data/$dataset/$dataset.json"; then
        echo "Failed to send HPO config to $target for $dataset!" >&2
        return 1
    fi
    return 0
}

function send_dataset {
    local IP=$1 NODE_ID=$2
    echo "Sending dataset $DATASET/node_$NODE_ID to $IP..."
    sshpass -p "$PASSWORD" ssh -n $ARGS "$USERNAME@$IP" "mkdir -p ~/flexfl/data/$DATASET" > /dev/null 2>&1 &&
    sshpass -p "$PASSWORD" scp $ARGS -r "data/$DATASET/node_$NODE_ID" "$USERNAME@$IP:~/flexfl/data/$DATASET" > /dev/null 2>&1 &&
    sshpass -p "$PASSWORD" ssh -n $ARGS "$USERNAME@$IP" "mv ~/flexfl/data/$DATASET/node_$NODE_ID ~/flexfl/data/$DATASET/my_data" > /dev/null 2>&1
    local rc=$?
    if [ $rc -ne 0 ]; then
        echo "Failed to send dataset to $IP!"
        return
    fi
    if ship_config "$USERNAME@$IP" "$DATASET" "$CONFIG_SRC"; then
        echo "Dataset sent to $IP successfully!"
    else
        echo "Dataset sent to $IP but HPO config transfer FAILED!"
    fi
}

main() {
    export $(grep -v '^#' .env | xargs)

    USERNAME=$VM_USERNAME
    PASSWORD=$VM_PASSWORD
    ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"

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
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
