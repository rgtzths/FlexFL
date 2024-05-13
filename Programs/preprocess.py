import argparse
from pathlib import Path

from config import DATASETS

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name (\"all\" to preprocess all datasets)")
args = parser.parse_args()

if args.dataset not in DATASETS and args.dataset != "all":
    raise ValueError(f"Dataset {args.dataset} not found")

datasets = list(DATASETS.keys()) if args.dataset == "all" else [args.dataset]

for dataset in datasets: 
    folder = Path(f"Data/{dataset}")
    dataset = DATASETS[dataset]()
    if not folder.exists():
        print("Downloadind data")
        dataset.download()
    print("Preprocessing data")
    dataset.preprocess()

