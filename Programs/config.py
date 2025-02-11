import sys
from pathlib import Path
import importlib.util
import inspect
from dotenv import load_dotenv
from typing import Generator

sys.path.append(".")
load_dotenv()

def get_classes(folder: str) -> dict[str, object]:
    """
    Gets all classes in a folder
    """
    classes = {}
    for class_path in Path(folder).rglob("*.py"):
        class_name = class_path.stem
        if class_name != "__init__":
            spec = importlib.util.spec_from_file_location(f"{folder}.{class_name}", class_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            classes[class_name] = getattr(module, class_name)
    return classes


def get_arguments(class_: object) -> Generator[tuple[str, type], None, None]:
    """
    Gets the arguments of a class
    """
    yield from {
        name: param.annotation
        for name, param in inspect.signature(class_).parameters.items()
    }.items()


FOLDERS: list[str] = [
    "Utils",
    "Comm",
    "Datasets",
    "Messages",
    "FL",
    "ML",
    "NeuralNetworks",
    "WorkerManagers",
]

MODULES: dict[str, dict[str, object]] = {
    module: get_classes(module) 
    for module in FOLDERS 
}

ALL_ARGS: dict[str, type] = {
    arg: type_
    for module in MODULES.values()
    for class_ in module.values()
    for arg, type_ in get_arguments(class_)
    if type_ in (int, float, str, bool)
}
