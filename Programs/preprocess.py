import argparse
from pathlib import Path

from config import DATASETS

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name (\"all\" to preprocess all datasets)", choices=["all",*DATASETS.keys()])
parser.add_argument("-v", "--val_size", type=float, default=0.15, help="Validation set size")
parser.add_argument("-t", "--test_size", type=float, default=0.15, help="Test set size")
args = parser.parse_args()

datasets = list(DATASETS.keys()) if args.dataset == "all" else [args.dataset]

for dataset in datasets: 
    folder = Path(f"Data/{dataset}")
    dataset = DATASETS[dataset]()
    print(f"\nDataset: {dataset.name}")
    if not folder.exists():
        dataset.download()
    dataset.preprocess(args.val_size, args.test_size)
    print("Done!")

