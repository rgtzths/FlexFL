
VM_LIST="scripts/ips.txt"

read -r MASTER_IP < "$VM_LIST"

while read -r IP; do
    ssh-keyscan -H $IP >> ~/.ssh/known_hosts
done < <(tail -n +2 "$VM_LIST")

sudo apt update -y
sudo dpkg --configure -a
sudo apt upgrade -y
sudo apt install -y python3.12-venv python3-dev libopenmpi-dev
mkdir flexfl
cd flexfl
python3 -m venv venv
echo "source $HOME/flexfl/venv/bin/activate" >> ~/.bashrc
source venv/bin/activate
pip install flexfl[all]

# TODO setup ntp server