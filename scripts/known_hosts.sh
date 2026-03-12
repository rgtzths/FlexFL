rm -f .ssh/known_hosts
rm -f .ssh/known_hosts.old

VM_LIST="scripts/ips.txt"
while read -r IP; do
    ssh-keyscan -H $IP >> ~/.ssh/known_hosts 2>/dev/null
done < "$VM_LIST" 

echo "SSH known_hosts updated."