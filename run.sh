# clear results
bash scripts/run_commands.sh "rm -rf flexfl/results"
sleep 5

# MPI
# warmup run
bash scripts/run_on_vms_mpi.sh --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5
# 3 runs
bash scripts/run_on_vms_mpi.sh --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5
bash scripts/run_on_vms_mpi.sh --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5
bash scripts/run_on_vms_mpi.sh --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5

# Zenoh
# warmup run
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5
# 3 runs
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5
bash scripts/run_on_vms.sh 0 0 --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5

# Zenoh with failures
bash scripts/run_on_vms.sh 1 0.01 --min_workers 7 --learning_rate 0.0001 --patience 10
sleep 5

# gather results
bash scripts/gather_results.sh