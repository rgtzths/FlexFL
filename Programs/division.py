import argparse

from config import DATASETS

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name (\"all\" to divide all datasets)", choices=["all",*DATASETS.keys()])
parser.add_argument("-n", "--num_workers", type=int, required=True, help="Number of workers (0 to divide for 2,4,8)")
args = parser.parse_args()

if args.num_workers < 0:
    raise ValueError("Number of workers must be greater or equal to 0")

datasets = list(DATASETS.keys()) if args.dataset == "all" else [args.dataset]
for dataset in datasets:
    dataset = DATASETS[dataset]()
    num_workers = [2, 4, 8] if args.num_workers == 0 else [args.num_workers]
    for nw in num_workers:
        print(f"Dividing {dataset.name} for {nw} workers")
        dataset.data_division(nw)
    
    