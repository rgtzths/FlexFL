#!/bin/bash

VM_LIST="scripts/ips.txt"

sudo swapoff -a
sudo apt update -y &&
sudo dpkg --configure -a &&
sudo apt upgrade -y &&

while read -r IP; do
    ssh-keyscan -H "$IP" >> ~/.ssh/known_hosts 2>/dev/null
done < "$VM_LIST" &&

sudo apt install -y python3.12-venv python3-dev libopenmpi-dev ntpsec &&
cd ~/flexfl &&
mkdir -p data results &&
python3 -m venv venv &&
source venv/bin/activate &&
pip install .[all]
