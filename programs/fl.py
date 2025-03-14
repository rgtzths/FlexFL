import argparse
import json
from config import get_modules_and_args, load_class
import os

FORBIDDEN_ARGS = {"self", "args", "kwargs", "ml", "wm", "nn", "dataset", "c", "m", "all_args"}

FOLDERS: list[str] = [
    "my_builtins",
    "fl_algorithms",
    "comms",
    "my_datasets",
    "message_layers",
    "ml_frameworks",
    "neural_networks",
]

MODULES, ALL_ARGS = get_modules_and_args(FOLDERS)

ALIASES = {
    "DecentralizedSync": "ds",
    "DecentralizedAsync": "da",
    "TensorFlow": "tf",
}

for m, classes in list(MODULES.items()):
    for class_name, path in list(classes.items()):
        MODULES[m][class_name.lower()] = path
        if class_name in ALIASES:
            MODULES[m][ALIASES[class_name]] = path

parser = argparse.ArgumentParser()
parser.add_argument('--config', type=str, help="Path to config JSON file", required=False)

parser.add_argument('-c', '--comm', type=str, help="Communication layer", choices=MODULES["comms"].keys(), default="Zenoh")
parser.add_argument('-d', '--dataset', type=str, help="Dataset", choices=MODULES["my_datasets"].keys(), default="IOT_DNL")
parser.add_argument('-m', '--message_layer', type=str, help="Message layer", choices=MODULES["message_layers"].keys(), default="Raw")
parser.add_argument('--nn', type=str, help="Neural network", choices=MODULES["neural_networks"].keys(), required=False)
parser.add_argument('--fl', type=str, help="Federated learning algorithm", choices=MODULES["fl_algorithms"].keys(), default="DecentralizedSync")
parser.add_argument('--ml', type=str, help="Machine learning framework", choices=MODULES["ml_frameworks"].keys(), default="TensorFlow")

for arg, (type_, value) in ALL_ARGS.items():
    if type_ == bool:
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
    args["min_workers"] = int(os.environ["OMPI_COMM_WORLD_SIZE"]) - 1

class_args = {k: v for k, v in args.items() if k not in FORBIDDEN_ARGS}

print("Importing modules...")
comm_class = load_class(MODULES["comms"][args["comm"]])
fl_class = load_class(MODULES["fl_algorithms"][args["fl"]])
nn_class = load_class(MODULES["neural_networks"][args["nn"]])
dataset_class = load_class(MODULES["my_datasets"][args["dataset"]])
message_class = load_class(MODULES["message_layers"][args["message_layer"]])
wm_class = load_class(MODULES["my_builtins"]["WorkerManager"])
ml_class = load_class(MODULES["ml_frameworks"][args["ml"]])
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