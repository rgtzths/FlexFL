import argparse
import json
from config import get_modules_and_args, load_class

FOLDERS: list[str] = [
    "utils",
    "comm",
    "my_datasets",
    "message_layers",
    "fl_algorithms",
    "ml_frameworks",
    "neural_networks",
    "worker_managers",
]

MODULES, ALL_ARGS = get_modules_and_args(FOLDERS)

ALIASES = {
    "DecentralizedSync": "ds",
    "TensorFlow": "tf",
}

for m, classes in list(MODULES.items()):
    for class_name, obj in list(classes.items()):
        MODULES[m][class_name.lower()] = obj
        if class_name in ALIASES:
            MODULES[m][ALIASES[class_name]] = obj

parser = argparse.ArgumentParser()
parser.add_argument('--config', type=str, help="Path to config JSON file", required=False)

parser.add_argument('-c', '--comm', type=str, help="Communication layer", choices=MODULES["comm"].keys(), default="Zenoh")
parser.add_argument('-d', '--dataset', type=str, help="Dataset", choices=MODULES["my_datasets"].keys(), default="IOT_DNL")
parser.add_argument('-m', '--message_layer', type=str, help="Message layer", choices=MODULES["message_layers"].keys(), default="Raw")
parser.add_argument('--nn', type=str, help="Neural network", choices=MODULES["neural_networks"].keys(), required=False)
parser.add_argument('--fl', type=str, help="Federated learning algorithm", choices=MODULES["fl_algorithms"].keys(), default="DecentralizedSync")
parser.add_argument('--ml', type=str, help="Machine learning framework", choices=MODULES["ml_frameworks"].keys(), default="TensorFlow")
parser.add_argument('--wm', type=str, help="Worker manager", choices=MODULES["worker_managers"].keys(), default="All")

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

print(args)