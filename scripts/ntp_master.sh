#!/bin/bash

sudo apt update
sudo apt install -y ntpsec

sudo bash -c "cat > /etc/ntp.conf" <<EOL
driftfile /var/lib/ntpsec/ntp.drift

# Allow unrestricted access (for internal network)
restrict default nomodify notrap nopeer noquery
restrict 127.0.0.1
restrict ::1

# Serve time to all clients
broadcast 192.168.1.255

EOL

sudo systemctl restart ntpsec.service
sudo systemctl enable ntpsec.service

# Verify the synchronization status
# ntpq -p
