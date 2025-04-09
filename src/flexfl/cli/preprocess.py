import argparse
from pathlib import Path

from flexfl.cli.utils import get_modules_and_args, load_class


def main():

    FOLDERS: list[str] = [
        "datasets",
    ]

    MODULES, _ = get_modules_and_args(FOLDERS)

    parser = argparse.ArgumentParser(description="Dataset preprocessing CLI")
    parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name (\"all\" to preprocess all datasets)", choices=["all", *MODULES["datasets"].keys()])
    parser.add_argument("-v", "--val_size", type=float, default=0.15, help="Default: float = 0.15")
    parser.add_argument("-t", "--test_size", type=float, default=0.15, help="Default: float = 0.15")
    args = parser.parse_args()

    datasets = list(MODULES["datasets"].keys()) if args.dataset == "all" else [args.dataset]

    for dataset in datasets: 
        folder = Path(f"data/{dataset}")
        dataset = load_class(MODULES["datasets"][dataset])()
        print(f"\nDataset: {dataset.name}")
        if not folder.exists():
            dataset.download()
        dataset.preprocess(args.val_size, args.test_size)
        print("Done!")


if __name__ == "__main__":
    main()