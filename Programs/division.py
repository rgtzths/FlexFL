import argparse
from pathlib import Path

from config import DATASETS

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name (\"all\" to preprocess all datasets)")
parser.add_argument("-n", "--num_workers", type=int, required=True, help="Number of workers")
args = parser.parse_args()

if args.dataset not in DATASETS and args.dataset != "all":
    raise ValueError(f"Dataset {args.dataset} not found")

datasets = list(DATASETS.keys()) if args.dataset == "all" else [args.dataset]
for dataset in datasets:
    dataset = DATASETS[dataset]()
    print(f"Dividing data for {dataset.name} dataset with {args.num_workers} workers")
    dataset.data_division(args.num_workers)
    