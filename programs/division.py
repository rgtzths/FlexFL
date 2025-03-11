import argparse
from pathlib import Path

from config import get_modules_and_args, load_class

FOLDERS: list[str] = [
    "my_datasets",
]

MODULES, ALL_ARGS = get_modules_and_args(FOLDERS)

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name (\"all\" to preprocess all datasets)", choices=["all", *MODULES["my_datasets"].keys()])
parser.add_argument("-n", "--num_workers", type=int, required=True, help="Number of workers")
parser.add_argument("-v", "--val_size", type=float, default=0, help="Default: float = 0.15")
parser.add_argument("-t", "--test_size", type=float, default=0, help="Default: float = 0.15")
args = parser.parse_args()

datasets = list(MODULES["my_datasets"].keys()) if args.dataset == "all" else [args.dataset]

for dataset in datasets: 
    dataset = load_class(MODULES["my_datasets"][dataset])()
    print(f"\nDividing dataset: {dataset.name}")
    dataset.data_division(args.num_workers, args.val_size, args.test_size)
    print("Done!")

