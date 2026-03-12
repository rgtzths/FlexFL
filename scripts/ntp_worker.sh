#!/bin/bash
# Script to set up a VM as an NTP worker that syncs to the master VM
# Run this script on each worker VM that needs to be synced

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

MASTER_IP=$1
if [ -z "$MASTER_IP" ]; then
  echo "Usage: $0 <master_ip>"
  echo "Please provide the IP address of the master NTP server."
  exit 1
fi

# Validate IP address format (basic check)
if [[ ! $MASTER_IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid IP address format. Please enter a valid IP address."
  exit 1
fi

# Install chrony if not already installed
apt-get update
apt-get install -y chrony

# Back up original config
cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak

# Create new configuration file
cat > /etc/chrony/chrony.conf << EOF
# Use the master VM as the only time source
server $MASTER_IP iburst minpoll 1 maxpoll 2

# Log clock adjustments of 0.1ms or more
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

# Wait for initial sync
echo "Waiting for initial synchronization..."
sleep 5

# Check status
echo "===== Worker NTP setup complete ====="
echo "Current time source status:"
chronyc tracking
echo ""
echo "Available sources:"
chronyc sources -v
echo ""
echo "Check offset value to see how closely synchronized you are to the master."
echo "For sub-millisecond precision, the offset should be less than 1 ms (0.001 seconds)."
