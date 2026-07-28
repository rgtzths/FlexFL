#!/bin/bash

set -e

VM_LIST="scripts/ips.txt"
APT_OPTS="-o DPkg::Lock::Timeout=600"

sudo swapoff -a || true

cloud-init status --wait > /dev/null 2>&1 || true

# cloud-init and unattended-upgrades can still hold the dpkg frontend lock here.
# apt waits for it via DPkg::Lock::Timeout, dpkg has no such option, so retry.
for _ in $(seq 1 60); do
    if sudo dpkg --configure -a; then
        break
    fi
    sleep 10
done

sudo apt update -y $APT_OPTS
sudo apt upgrade -y $APT_OPTS

while read -r IP; do
    ssh-keyscan -H "$IP" >> ~/.ssh/known_hosts 2>/dev/null || true
done < "$VM_LIST"

sudo apt install -y $APT_OPTS python3.12-venv python3-dev libopenmpi-dev ntpsec
cd ~/flexfl
mkdir -p data results
python3 -m venv venv
source venv/bin/activate
pip install .[all]
