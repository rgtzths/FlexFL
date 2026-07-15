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


def _literal_default(default: ast.expr | None) -> object:
    """
    Evaluate a kwonly default AST node to its Python value for display. Handles
    negative/None/expression defaults (e.g. `= -1` → ast.UnaryOp) that have no
    `.value` attribute; falls back to the source text for non-literal defaults
    (names, calls) rather than crashing CLI discovery.
    """
    if default is None:
        return None
    try:
        return ast.literal_eval(default)
    except (ValueError, SyntaxError, TypeError):
        return ast.unparse(default)


def get_args_from_node(node: ast.FunctionDef) -> dict[str, tuple[type, object]]:
    args = {}
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        if not arg.annotation:
            continue
        arg_type = ALLOWED_TYPES.get(ast.unparse(arg.annotation), None)
        if arg_type is not None:
            args[arg.arg] = (arg_type, _literal_default(default))
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


def get_modules_and_args(folders: list[str]) -> tuple[dict[str, dict[str, str]], dict[str, tuple[type, object]]]:
    modules: dict[str, dict[str, object]] = {
        module: get_classes(f"{Path(__file__).parent.parent}/{module}")
        for module in folders
    }
    # Merge kwonly args across all discovered classes into a single flag set.
    # Iterate deterministically (rglob order is filesystem-dependent) so the
    # displayed default for a shared arg is stable. Sibling classes intentionally
    # share flags (e.g. every comm has `ip`/`is_anchor`), so an identical-type
    # duplicate is kept silently; only an *incompatible-type* collision — which
    # would misconfigure a single `--flag` — is a hard error at startup.
    args: dict[str, tuple[type, object]] = {}
    owners: dict[str, str] = {}
    for module in modules.values():
        for class_name, class_path in sorted(module.items()):
            for arg, (type_, value) in get_args_from_file(class_path).items():
                if arg in args:
                    prev_type, _ = args[arg]
                    if prev_type is not type_:
                        raise ValueError(
                            f"CLI argument name collision: '--{arg}' is declared with "
                            f"incompatible types by {owners[arg]} ({prev_type.__name__}) "
                            f"and {class_name} ({type_.__name__}). They would share one "
                            f"CLI flag — rename one (e.g. prefix it, as with 'ca_penalty')."
                        )
                    continue
                args[arg] = (type_, value)
                owners[arg] = class_name
    return modules, args


def load_class(filename: str) -> type:
    class_name = Path(filename).stem
    spec = importlib.util.spec_from_file_location(class_name, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)