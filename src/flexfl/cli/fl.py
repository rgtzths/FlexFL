import argparse
import json
import os

from flexfl.cli.utils import get_modules_and_args, load_class


def main():

    FORBIDDEN_ARGS = {"self", "args", "kwargs", "ml", "wm", "nn", "dataset", "c", "m", "all_args"}

    FOLDERS: list[str] = [
        "builtins",
        "fl_algos",
        "comms",
        "datasets",
        "msg_layers",
        "ml_fw",
        "neural_nets",  
    ]

    MODULES, ALL_ARGS = get_modules_and_args(FOLDERS)

    ALIASES = {
        "DecentralizedSync": "ds",
        "DecentralizedAsync": "da",
        "TensorFlow": "tf",
        "PyTorch": "torch",
    }

    for m, classes in list(MODULES.items()):
        for class_name, path in list(classes.items()):
            MODULES[m][class_name.lower()] = path
            if class_name in ALIASES:
                MODULES[m][ALIASES[class_name]] = path

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, help="Path to config JSON file", required=False)

    parser.add_argument('-c', '--comm', type=str, help="Communication layer", choices=MODULES["comms"].keys(), default="Zenoh")
    parser.add_argument('-d', '--dataset', type=str, help="Dataset", choices=MODULES["datasets"].keys(), default="IOT_DNL")
    parser.add_argument('-m', '--message_layer', type=str, help="Message layer", choices=MODULES["msg_layers"].keys(), default="Raw")
    parser.add_argument('--nn', type=str, help="Neural network", choices=MODULES["neural_nets"].keys(), required=False)
    parser.add_argument('--fl', type=str, help="Federated learning algorithm", choices=MODULES["fl_algos"].keys(), default="DecentralizedSync")
    parser.add_argument('--ml', type=str, help="Machine learning framework", choices=MODULES["ml_fw"].keys(), default="TensorFlow")

    for arg, (type_, value) in ALL_ARGS.items():
        if type_ is bool:
            parser.add_argument(f'--{arg}', action=argparse.BooleanOptionalAction, required=False, help=f"Default: {type_.__name__} = {value}")
        else:
            parser.add_argument(f'--{arg}', type=type_, required=False, help=f"Default: {type_.__name__} = {value}")

    args = parser.parse_args()
    if args.config is not None:
        with open(args.config, 'r') as f:
            config = json.load(f)
        parser.set_defaults(**config)
    args = parser.parse_args()
    args = {k: v for k, v in vars(args).items() if v is not None}

    if "nn" not in args:
        args["nn"] = args["dataset"]
    if "OMPI_COMM_WORLD_SIZE" in os.environ:
        args["comm"] = "MPI"
        if "min_workers" not in args:
            args["min_workers"] = int(os.environ["OMPI_COMM_WORLD_SIZE"]) - 1

    class_args = {k: v for k, v in args.items() if k not in FORBIDDEN_ARGS}

    print("Importing modules...")
    comm_class = load_class(MODULES["comms"][args["comm"]])
    fl_class = load_class(MODULES["fl_algos"][args["fl"]])
    nn_class = load_class(MODULES["neural_nets"][args["nn"]])
    dataset_class = load_class(MODULES["datasets"][args["dataset"]])
    message_class = load_class(MODULES["msg_layers"][args["message_layer"]])
    wm_class = load_class(MODULES["builtins"]["WorkerManager"])
    ml_class = load_class(MODULES["ml_fw"][args["ml"]])
    print("Modules imported")

    f = fl_class(
        ml=ml_class(
            nn=nn_class(**class_args),
            dataset=dataset_class(**class_args),
            **class_args,
        ),
        wm=wm_class(
            c=comm_class(**class_args),
            m=message_class(**class_args),
            **class_args,
        ),
        all_args=args,
        **class_args,
    )

    try:
        f.run()
    except KeyboardInterrupt:
        print("\nForcing end...")
        f.force_end()


if __name__ == "__main__":
    main()