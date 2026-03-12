import argparse

from flexfl.cli.utils import get_modules_and_args, load_class


def main():

    FOLDERS: list[str] = [
        "datasets",
    ]

    MODULES, ALL_ARGS = get_modules_and_args(FOLDERS)

    parser = argparse.ArgumentParser(description="Dataset division CLI")
    parser.add_argument("-d", "--dataset", type=str, required=True, help="Dataset name (\"all\" to preprocess all datasets)", choices=["all", *MODULES["datasets"].keys()])
    parser.add_argument("-n", "--num_workers", type=int, required=True, help="Number of workers")
    parser.add_argument("-v", "--val_size", type=float, default=0, help="Default: float = 0 - The size of the validation dataset in the worker")
    parser.add_argument("-t", "--test_size", type=float, default=0, help="Default: float = 0 - The size of the test dataset in the worker")
    parser.add_argument("-s", "--split_distribution", type=str, default='iid', help="Default: str = iid")
    parser.add_argument("-p", "--distribution_percentage", type=float, default=0.9 , help="Default: float = 0.9 - The inclass workers will have 90 percent of the examples")


    for arg, (type_, value) in ALL_ARGS.items():
        if type_ is bool:
            parser.add_argument(f'--{arg}', action=argparse.BooleanOptionalAction, required=False, help=f"Default: {type_.__name__} = {value}")
        else:
            parser.add_argument(f'--{arg}', type=type_, required=False, help=f"Default: {type_.__name__} = {value}")

    args = parser.parse_args()

    datasets = list(MODULES["datasets"].keys()) if args.dataset == "all" else [args.dataset]

    for dataset in datasets: 
        dataset = load_class(MODULES["datasets"][dataset])(data_name = args.data_name, data_folder=args.data_folder)
        print(f"\nDividing dataset: {dataset.name}")
        dataset.data_division(args.num_workers, args.val_size, args.test_size, args.split_distribution, args.distribution_percentage)
        print("Done!")


if __name__ == "__main__":
    main()

