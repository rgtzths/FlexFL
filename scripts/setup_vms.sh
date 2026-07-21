#!/bin/bash

export $(grep -v '^#' .env | xargs)

KEY_NAME="id_rsa"
KEY_PATH="keys/$KEY_NAME"
USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
export SSHPASS="$PASSWORD"
VM_LIST="scripts/ips.txt"
FLEXFL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
    echo "Usage: $0 [-f <ips_file>]" >&2
    echo "Example: $0 -f scripts/ips_all.txt" >&2
}

while getopts ":f:" opt; do
    case "$opt" in
        f) VM_LIST="$OPTARG" ;;
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

if [ ! -f "$KEY_PATH" ]; then
    echo "Generating SSH key..."
    mkdir -p keys
    ssh-keygen -t rsa -b 4096 -f "$KEY_PATH" -N "" > /dev/null 2>&1
    echo "SSH key generated at $KEY_PATH"
fi

if ! command -v sshpass >/dev/null 2>&1; then
    echo "Error: sshpass not found on this control host." >&2
    echo "Install it and re-run, e.g.:" >&2
    echo "  Debian/Ubuntu: sudo apt install -y sshpass" >&2
    echo "  Arch/CachyOS:  sudo pacman -S sshpass" >&2
    echo "  Fedora:        sudo dnf install -y sshpass" >&2
    echo "  macOS:         brew install sshpass" >&2
    exit 1
fi

function setup_worker {
    local IP=$1
    echo "Setting up $IP..."
    sshpass -p "$PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -f -i "$KEY_PATH.pub" "$USERNAME@$IP" > /dev/null 2>&1 &&
    sshpass -p "$PASSWORD" scp $ARGS "$KEY_PATH" "$USERNAME@$IP:~/.ssh/" &&
    sshpass -p "$PASSWORD" scp $ARGS "$KEY_PATH.pub" "$USERNAME@$IP:~/.ssh/" &&
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "chmod 600 ~/.ssh/$KEY_NAME && touch ~/.ssh/known_hosts && mkdir -p ~/scripts" &&
    sshpass -p "$PASSWORD" scp $ARGS "$VM_LIST" "$USERNAME@$IP:~/scripts/ips.txt" &&
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "mkdir -p ~/flexfl" &&
    rsync -az --exclude='data/' --exclude='results/' \
        --rsh='sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q' \
        "$FLEXFL_DIR/" "$USERNAME@$IP:~/flexfl/" &&
    sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$IP" "bash ~/flexfl/scripts/vm.sh"
    if [ $? -eq 0 ]; then
        echo "Setup completed successfully on $IP."
    else
        echo "Error: Setup failed on $IP."
    fi
}

while read -r IP_; do
    if [[ -z "$IP_" || "$IP_" =~ ^# ]]; then
        continue
    fi
    setup_worker "$IP_" &
done < "$VM_LIST"
wait

echo "SSH setup completed!"
