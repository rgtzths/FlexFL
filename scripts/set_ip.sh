#!/bin/bash

# Get the IP address of the host machine
HOST_IP=$(hostname -I | awk '{print $1}')

echo "Host IP address: $HOST_IP"

# Export the HOST_IP as an environment variable
export HOST_IP="$HOST_IP"