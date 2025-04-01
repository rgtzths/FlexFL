#!/bin/bash

VM_LIST="scripts/ips.txt"
read -r MASTER_IP < "$VM_LIST"

sudo apt update
sudo apt install -y ntpsec

sudo bash -c "cat > /etc/ntp.conf" <<EOL
driftfile /var/lib/ntpsec/ntp.drift

# Sync time with NTP Master Server
server $MASTER_IP iburst

# Allow unrestricted access
restrict default nomodify notrap nopeer noquery
restrict 127.0.0.1
restrict ::1

EOL

sudo systemctl restart ntpsec.service
sudo systemctl enable ntpsec.service

# Verify synchronization status with the master
# ntpq -p