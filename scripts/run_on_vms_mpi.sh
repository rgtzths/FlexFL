#!/bin/bash

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

VM_LIST="scripts/ips.txt" # needs to end in empty line
USERNAME=$VM_USERNAME
PASSWORD=$VM_PASSWORD
ARGS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"
RUN_ARGS=$@

if [ ! -f "$VM_LIST" ]; then
    echo "Error: VM list file '$VM_LIST' not found!"
    exit 1
fi

read -r MASTER_IP < "$VM_LIST"
NWORKERS=$(wc -l < "$VM_LIST")

sshpass -p "$PASSWORD" scp $ARGS "$VM_LIST" "$USERNAME@$MASTER_IP:~/$VM_LIST"
sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$MASTER_IP" "mv $VM_LIST flexfl/ips.txt"
sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$MASTER_IP" "sed -i '1s/.*/127.0.0.1/' flexfl/ips.txt"
sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$MASTER_IP" "sed -i 's/$/ slots=1 max_slots=1/' flexfl/ips.txt" 

COMMAND="mpirun -n $NWORKERS --hostfile ips.txt bash -c \"source venv/bin/activate; flexfl --no-save_model --data_folder my_data $RUN_ARGS\""
sshpass -p "$PASSWORD" ssh $ARGS "$USERNAME@$MASTER_IP" "cd flexfl && screen -dmS fl-master $COMMAND"
sshpass -p "$PASSWORD" ssh -tt $ARGS "$USERNAME@$MASTER_IP" "screen -r fl-master"

echo "Done!"
