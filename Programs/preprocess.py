import argparse
from pathlib import Path

from config import DATASETS

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name (\"all\" to preprocess all datasets)")
parser.add_argument("-v", "--val_size", type=float, default=0.15, help="Validation set size")
parser.add_argument("-t", "--test_size", type=float, default=0.15, help="Test set size")
args = parser.parse_args()

if args.dataset not in DATASETS and args.dataset != "all":
    raise ValueError(f"Dataset {args.dataset} not found")

datasets = list(DATASETS.keys()) if args.dataset == "all" else [args.dataset]

for dataset in datasets: 
    folder = Path(f"Data/{dataset}")
    dataset = DATASETS[dataset]()
    print(f"\nDataset: {dataset.name}")
    if not folder.exists():
        dataset.download()
    dataset.preprocess(args.val_size, args.test_size)
    print("Done!")

