from pathlib import Path
import importlib.util
import ast
from dotenv import load_dotenv

load_dotenv()

ALLOWED_TYPES = {"int": int, "str": str, "float": float, "bool": bool}

def get_classes(folder: str) -> dict[str, str]:
    classes = {}
    for class_path in Path(folder).rglob("*.py"):
        class_name = class_path.stem
        if class_name != "__init__":
            with open(class_path, "r", encoding="utf-8") as file:
                tree = ast.parse(file.read(), filename=class_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    classes[node.name] = str(class_path)
    return classes


def get_args_from_node(node: ast.FunctionDef) -> dict[str, tuple[type, str]]:
    args = {}
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        arg_name = arg.arg
        arg_type = None
        value = default.value if default else None
        if arg.annotation:
            arg_type_str = ast.unparse(arg.annotation)
            arg_type = ALLOWED_TYPES.get(arg_type_str, None)
        if arg_type is not None:
            args[arg_name] = (arg_type, value)
    return args


def get_args_from_file(filename: str) -> dict[str, tuple[type, str]]:
    with open(filename, "r", encoding="utf-8") as file:
        tree = ast.parse(file.read(), filename=filename)
    class_name = Path(filename).stem
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for subnode in node.body:
            if not isinstance(subnode, ast.FunctionDef) or subnode.name != "__init__":
                continue
            return get_args_from_node(subnode)
    return {}


def get_modules_and_args(folders: list[str]) -> tuple[dict[str, dict[str, str]], dict[str, tuple[type, str]]]:
    modules: dict[str, dict[str, object]] = {
        module: get_classes(f"{Path(__file__).parent.parent}/{module}")
        for module in folders 
    }
    args: dict[str, tuple[type, str]] = {
        arg: val
        for module in modules.values()
        for class_ in module.values()
        for arg, val in get_args_from_file(class_).items()
    }
    return modules, args


def load_class(filename: str) -> type:
    class_name = Path(filename).stem
    spec = importlib.util.spec_from_file_location(class_name, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)