#!/bin/bash

export $(grep -v '^#' .env | xargs)

USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
VERBOSE=0
ONLY_WORKERS=0
RUN_FILE=0
VM_LIST="scripts/ips.txt"

usage() {
    echo "Usage: $0 [-v] [-w] [-i <ips_file>] [-f <script_file>] <command>" >&2
    echo "  -v: verbose mode" >&2
    echo "  -w: run command only on workers (skip first IP)" >&2
    echo "  -i: path to IPs file (default: scripts/ips.txt)" >&2
    echo "  -f: run a local script file on the VMs" >&2
}

while getopts ":vwi:f:" opt; do
    case "$opt" in
        v) VERBOSE=1 ;;
        w) ONLY_WORKERS=1 ;;
        i) VM_LIST="$OPTARG" ;;
        f) RUN_FILE=1; FILE="$OPTARG" ;;
        *)
            usage
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

if [ $# -eq 0 ] && [ $RUN_FILE -eq 0 ]; then
    usage
    exit 1
fi

COMMAND=$@

if [ $RUN_FILE -eq 1 ]; then
    if [ ! -f "$FILE" ]; then
        echo "Error: File $FILE not found."
        exit 1
    fi
    COMMAND="sudo bash /tmp/$FILE"
fi

if [ ! -f "$VM_LIST" ]; then
    echo "Error: VM list file '$VM_LIST' not found!"
    exit 1
fi

echo "Command to execute: $COMMAND"

read -r MASTER_IP < "$VM_LIST"

function run_command {
    local IP=$1
    if [ $RUN_FILE -eq 1 ]; then
        sshpass -p "$PASSWORD" scp $ARGS "$FILE" "$USERNAME@$IP:/tmp/$FILE"
    fi
    if [ $VERBOSE -eq 0 ]; then
        sshpass -p "$PASSWORD" ssh -tt $ARGS "$USERNAME@$IP" "bash -i -c '$COMMAND'" > /dev/null 2>&1
    else
        sshpass -p "$PASSWORD" ssh -tt $ARGS "$USERNAME@$IP" "bash -i -c '$COMMAND'"
    fi
    if [ $? -eq 0 ]; then
        echo "Command executed successfully on $IP."
    else
        echo "Error: Command failed on $IP."
    fi
}

while read -r IP; do
    if [[ -z "$IP" || "$IP" =~ ^# ]]; then
        continue
    fi
    if [ $ONLY_WORKERS -eq 1 ] && [ "$IP" == "$MASTER_IP" ]; then
        continue
    fi
    run_command "$IP" &
done < "$VM_LIST"
wait
echo "Command execution completed!"
