#!/bin/bash

if [ $# -eq 0 ]; then
    echo "Usage: $0 [-v] <command>"
    echo "  -v: verbose mode"
    exit 1
fi

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

VM_LIST="scripts/ips.txt" # needs to end in empty line
USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"

if [ "$1" == "-v" ]; then
    VERBOSE=1
    shift
else
    VERBOSE=0
fi
COMMAND=$@

echo "Command to execute: $@"

function run_command {
    local IP=$1
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
    run_command "$IP" &
done < "$VM_LIST"
wait
echo "Command execution completed!"