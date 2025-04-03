#!/bin/bash
# Script to set up a VM as an NTP master time server
# Run this script on the VM that will act as the time source

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

# Install chrony if not already installed
apt-get update
apt-get install -y chrony

# Back up original config
cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak

# Create new configuration file
cat > /etc/chrony/chrony.conf << EOF
# Connect to external NTP servers
server 0.pool.ntp.org iburst minpoll 4 maxpoll 4
server 1.pool.ntp.org iburst minpoll 4 maxpoll 4

# Allow this VM to act as a time server
local stratum 8

# Allow any client to connect
allow all

# Log clock adjustments
logchange 0.0001

# Speed up initial sync
makestep 0.1 3

# Enable kernel synchronization
hwtimestamp *

# Log file location
logdir /var/log/chrony
EOF

# Restart chrony to apply changes
systemctl restart chronyd

# Check status
echo "===== Master NTP server setup complete ====="
echo "Current time source status:"
chronyc tracking
echo ""
echo "Available sources:"
chronyc sources -v
echo ""
echo "Your master NTP server IP address is:"
hostname -I | awk '{print $1}'
echo "Share this IP with worker VMs"
