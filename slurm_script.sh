#!/bin/bash
#SBATCH --job-name=Hyperparameter_Importance
#SBATCH --nodes=1 # Request 1 nodes
#SBATCH --ntasks=1 # Nº of Processes per node
#SBATCH --cpus-per-task=2 # Requests 2 CPUs to assist in each task
#SBATCH --gres=gpu:RTXa4000:1 # Requests 1 GPU per task
#SBATCH --gpu-bind=single:1
#SBATCH --partition=gpuPartition # Partition
#SBATCH --output=%x_%j.out      ### Slurm Output file, %x is job name, %j is job id
#SBATCH --mem=16 # memory reserved for the job

# Load the Python environment
#source venv/bin/activate

#If there is only one script/value combination to run, remove the (#SBATCH --array=0-5)
#And run something like
srun uv run python model_finder/model_finder.py