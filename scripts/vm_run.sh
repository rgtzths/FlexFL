#!/bin/bash

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

VM_LIST="scripts/ips.txt" # needs to end in empty line
USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
COMMAND=$@
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"

echo "Command to execute: $@"
echo ""


function run_command {
    local IP=$1
    sshpass -p "$PASSWORD" ssh -tt $ARGS "$USERNAME@$IP" "bash -i -c '$COMMAND'"
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