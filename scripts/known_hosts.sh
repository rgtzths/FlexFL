#!/bin/bash

VM_LIST="${1:-scripts/ips.txt}"

rm -f ~/.ssh/known_hosts
rm -f ~/.ssh/known_hosts.old

while read -r IP; do
    ssh-keyscan -H "$IP" >> ~/.ssh/known_hosts 2>/dev/null
done < "$VM_LIST"

echo "SSH known_hosts updated."
