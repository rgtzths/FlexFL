
# MPI
# warmup run
bash scripts/run_on_vms_mpi.sh --learning_rate 0.0001 --patience 10
# 3 runs
bash scripts/run_on_vms_mpi.sh --learning_rate 0.0001 --patience 10
bash scripts/run_on_vms_mpi.sh --learning_rate 0.0001 --patience 10
bash scripts/run_on_vms_mpi.sh --learning_rate 0.0001 --patience 10

# Zenoh
# warmup run
bash scripts/run_on_vms.sh 0 0 --min_workers 10 --learning_rate 0.0001 --patience 10
# 3 runs
bash scripts/run_on_vms.sh 0 0 --min_workers 10 --learning_rate 0.0001 --patience 10
bash scripts/run_on_vms.sh 0 0 --min_workers 10 --learning_rate 0.0001 --patience 10
bash scripts/run_on_vms.sh 0 0 --min_workers 10 --learning_rate 0.0001 --patience 10
