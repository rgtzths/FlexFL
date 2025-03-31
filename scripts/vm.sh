
VM_LIST="scripts/ips.txt"

while read -r IP; do
    ssh-keyscan -H $IP >> ~/.ssh/known_hosts
done < "$VM_LIST"

sudo apt update -y
sudo dpkg --configure -a
sudo apt upgrade -y
sudo apt install -y python3.12-venv python3-dev libopenmpi-dev