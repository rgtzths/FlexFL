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

# Copy one local directory into a VM directory. Overridable in tests.
# Args: <user@ip> <local_dir> <remote_parent_dir>
copy_dir_to_vm() {
    sshpass -p "$PASSWORD" scp $ARGS -r "$2" "$1:$3" > /dev/null 2>&1
}

# Run a command on a VM and print its stdout. Overridable in tests.
# Args: <user@ip> <command>
run_on_vm() {
    sshpass -p "$PASSWORD" ssh -n $ARGS "$1" "$2" 2>/dev/null
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

# Print "<sha256>  <file>" for every .npy file in a local directory.
# Args: <dir>
local_npy_manifest() {
    (cd "$1" && sha256sum -- *.npy)
}

# Ship node_<id> to a VM as my_data, replacing any previous my_data, and
# verify it against the local partition byte for byte.
# Args: <ip> <node_id>
function send_dataset {
    local IP=$1 NODE_ID=$2
    local target="$USERNAME@$IP"
    local src="data/$DATASET/node_$NODE_ID"
    local remote="~/flexfl/data/$DATASET"
    local required="x_train.npy y_train.npy"
    local f expected actual
    [ "$NODE_ID" -eq 0 ] && required="x_val.npy y_val.npy"
    grep -q '"target": {' "data/$DATASET/_data/scaling.json" 2>/dev/null &&
        required="$required target_scaling.json"
    echo "Sending dataset $DATASET/node_$NODE_ID to $IP..."
    for f in $required; do
        if [ ! -f "$src/$f" ]; then
            echo "Failed to send dataset to $IP: missing local $src/$f!" >&2
            return 1
        fi
    done
    if ! expected="$(local_npy_manifest "$src")"; then
        echo "Failed to send dataset to $IP: cannot hash local $src!" >&2
        return 1
    fi
    # A leftover my_data makes the mv below nest node_<id> inside it, and the
    # workers then train on the stale files.
    if ! run_on_vm "$target" "rm -rf $remote/my_data $remote/node_$NODE_ID && mkdir -p $remote" > /dev/null; then
        echo "Failed to send dataset to $IP: remote cleanup failed!" >&2
        return 1
    fi
    if ! copy_dir_to_vm "$target" "$src" "$remote"; then
        echo "Failed to send dataset to $IP: copy failed!" >&2
        return 1
    fi
    if ! run_on_vm "$target" "mv $remote/node_$NODE_ID $remote/my_data" > /dev/null; then
        echo "Failed to send dataset to $IP: rename to my_data failed!" >&2
        return 1
    fi
    if ! actual="$(run_on_vm "$target" "cd $remote/my_data && sha256sum -- *.npy")"; then
        echo "Failed to send dataset to $IP: cannot hash remote my_data!" >&2
        return 1
    fi
    if [ "$actual" != "$expected" ]; then
        echo "Failed to send dataset to $IP: my_data checksum mismatch with $src!" >&2
        return 1
    fi
    if ! ship_config "$target" "$DATASET" "$CONFIG_SRC"; then
        echo "Dataset sent to $IP but HPO config transfer FAILED!" >&2
        return 1
    fi
    echo "Dataset sent to $IP successfully!"
    return 0
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

    # DATASET is interpolated unquoted into remote rm -rf commands.
    if [[ ! "$DATASET" =~ ^[A-Za-z0-9._-]+$ ]]; then
        echo "Error: invalid dataset name '$DATASET'!" >&2
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
    pids=()
    while read -r IP; do
        if [[ -z "$IP" || "$IP" =~ ^# ]]; then
            continue
        fi
        send_dataset "$IP" "$NODE_ID" &
        pids+=("$!")
        NODE_ID=$((NODE_ID + 1))
    done < "$VM_LIST"
    if [ "${#pids[@]}" -eq 0 ]; then
        echo "Error: no VMs listed in '$VM_LIST'!" >&2
        exit 1
    fi
    failed=0
    for pid in "${pids[@]}"; do
        wait "$pid" || failed=$((failed + 1))
    done
    if [ "$failed" -ne 0 ]; then
        echo "Dataset setup FAILED on $failed VM(s)!" >&2
        exit 1
    fi
    echo "Dataset setup completed!"
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
