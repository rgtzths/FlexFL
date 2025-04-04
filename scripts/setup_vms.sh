#!/bin/bash

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

KEY_NAME="id_rsa"
KEY_PATH="keys/$KEY_NAME"
VM_LIST="scripts/ips.txt" # needs to end in empty line
USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"

# Check VM list
if [ ! -f "$VM_LIST" ]; then
    echo "Error: VM list file '$VM_LIST' not found!"
    exit 1
fi

# Generate SSH key if it doesn't exist
if [ ! -f "$KEY_PATH" ]; then
    echo "Generating SSH key..."
    mkdir -p keys
    ssh-keygen -t rsa -b 4096 -f "$KEY_PATH" -N "" > /dev/null 2>&1
    echo "SSH key generated at $KEY_PATH"
fi

sudo apt install -y sshpass

function setup_worker {
    local IP=$1
    echo "Setting up $IP..."
    sshpass -p "$PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -f -i "$KEY_PATH.pub" "$USERNAME@$IP" > /dev/null 2>&1 &&
    sshpass -p "$PASSWORD" scp $ARGS "$KEY_PATH" "$USERNAME@$IP:~/.ssh/" &&
    sshpass -p "$PASSWORD" scp $ARGS "$KEY_PATH.pub" "$USERNAME@$IP:~/.ssh/" &&
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "chmod 600 ~/.ssh/$KEY_NAME && touch ~/.ssh/known_hosts && mkdir scripts" &&
    sshpass -p "$PASSWORD" scp $ARGS "$VM_LIST" "$USERNAME@$IP:~/$VM_LIST" &&
    sshpass -p "$PASSWORD" scp $ARGS "scripts/vm.sh" "$USERNAME@$IP:~/scripts/vm.sh" &&
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "bash ~/scripts/vm.sh" > /dev/null 2>&1 
    if [ $? -eq 0 ]; then
        echo "Setup completed successfully on $IP."
    else
        echo "Error: Setup failed on $IP."
    fi
}

# Copy SSH key to each VM
while read -r IP_; do
    if [[ -z "$IP_" || "$IP_" =~ ^# ]]; then
        continue
    fi
    setup_worker "$IP_" &
done < "$VM_LIST"
# Wait for all background jobs to finish
wait

echo "SSH setup completed!"
