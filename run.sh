# Clear results
bash scripts/run_commands.sh "rm -rf flexfl/results"

# No failures - decentralized async
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh

bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka

bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt

# Failures - decentralized async
bash scripts/run_on_vms.sh 10 0.01 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 10 0.01 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 10 0.05 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 10 0.05 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 10 0.1 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh
bash scripts/run_on_vms.sh 10 0.1 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c zenoh

bash scripts/run_on_vms.sh 10 0.01 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 10 0.01 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 10 0.05 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 10 0.05 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 10 0.1 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka
bash scripts/run_on_vms.sh 10 0.1 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c kafka

bash scripts/run_on_vms.sh 10 0.01 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 10 0.01 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 10 0.05 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 10 0.05 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 10 0.1 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt
bash scripts/run_on_vms.sh 10 0.1 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl da -c mqtt

# No failures - decentralized sync
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c zenoh

bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c kafka

bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl ds -c mqtt

# Failures - centralized sync
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c zenoh
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c zenoh

bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c kafka
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c kafka

bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c mqtt
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10 --fl cs -c mqtt

# Gather results
bash scripts/gather_results.sh
