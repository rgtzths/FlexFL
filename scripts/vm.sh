#!/bin/bash

set -e

VM_LIST="scripts/ips.txt"
APT_OPTS="-o DPkg::Lock::Timeout=600"
APT_RETRIES="${APT_RETRIES:-5}"
APT_RETRY_DELAY="${APT_RETRY_DELAY:-30}"

apt_retry() {
    local attempt
    for attempt in $(seq 1 "$APT_RETRIES"); do
        if sudo apt "$@" -y $APT_OPTS; then
            return 0
        fi
        if [ "$attempt" -lt "$APT_RETRIES" ]; then
            echo "apt $1 failed (attempt $attempt/$APT_RETRIES) — retrying in ${APT_RETRY_DELAY}s" >&2
            sleep "$APT_RETRY_DELAY"
        fi
    done
    echo "apt $1 failed after $APT_RETRIES attempts" >&2
    return 1
}

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

apt_retry update
apt_retry upgrade

while read -r IP; do
    ssh-keyscan -H "$IP" >> ~/.ssh/known_hosts 2>/dev/null || true
done < "$VM_LIST"

apt_retry install python3.12-venv python3-dev libopenmpi-dev ntpsec
cd ~/flexfl
mkdir -p data results
python3 -m venv venv
source venv/bin/activate
pip install .[all]
