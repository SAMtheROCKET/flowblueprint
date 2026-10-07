"""Read a script and the local modules it imports, without running them.

Files are decoded the way Python decodes source (coding cookie or
UTF-8) and parsed with the standard library's ast module. No target
code is imported or executed; the original files are never changed.
"""

import ast
from dataclasses import dataclass, field
import io
from pathlib import Path
import re
import tokenize

from refactrail.notebooks import read_cell_source_str, read_notebook_dict

# IPython magics and shell escapes: not Python, so not drawn.
MAGIC_LINE_PATTERN = re.compile(r"^(\s*)([%!].*)$", re.MULTILINE)
# "# %% Title" cell markers (VS Code, Jupytext, Spyder) and the markers
# FlowBlueprint writes for notebook Markdown headings.
SECTION_PATTERN = re.compile(r"^#\s*%%(?:\s*\[markdown\])?\s+(\S.*?)\s*$")
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(\S.*?)\s*#*\s*$")

@dataclass
class FunctionInfo:
    """What the source says about a function, without running it.

    Args:
        name: The function name.
        summary: The first line of its docstring, or "".
        parameters: (name, annotation) pairs; annotation "" when absent.
        returns: The return annotation as written, or "".
        module: The developed module it is defined in ("" for the
            script itself).
        line: The line of the def statement.
        body: The function's statements (kept so a script function
            that carries the whole flow can be drawn step by step).
        owner_class: The class a method belongs to, else "".
        source_path: The developed module's file, or None for the
            script itself.
    """

    name: str
    summary: str = ""
    parameters: list[tuple[str, str]] = field(default_factory=list)
    returns: str = ""
    module: str = ""
    line: int = 0
    body: list[ast.stmt] = field(default_factory=list, repr=False,
                                 compare=False)
    owner_class: str = ""
    source_path: Path | None = None


@dataclass
class ClassInfo:
    """What the source says about a class, without running it.

    Args:
        name: The class name.
        summary: The first line of its docstring, or "".
        methods: Its methods by name.
        module: The developed module it is defined in ("" for the
            script itself).
    """

    name: str
    summary: str = ""
    methods: dict[str, FunctionInfo] = field(default_factory=dict)
    module: str = ""


@dataclass
class ScriptInfo:
    """A parsed script and the names it can call.

    Args:
        path: The script file.
        tree: Its syntax tree.
        functions: Functions defined in the script, by name.
        imported: Local name -> (module, original name) for every
            import; original name is "" for "import module".
        developed: Functions of developed (local) modules, by the
            local name the script uses for them.
        developed_modules: Local name -> module for "import module" of
            a developed module.
        classes: Classes of the script and of developed modules, by the
            name the script uses for them ("Model" or "models.Model").
        sections: (line, title) of each section heading, in order.
    """

    path: Path
    tree: ast.Module
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    imported: dict[str, tuple[str, str]] = field(default_factory=dict)
    developed: dict[str, FunctionInfo] = field(default_factory=dict)
    developed_modules: dict[str, str] = field(default_factory=dict)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    sections: list[tuple[int, str]] = field(default_factory=list)


def read_source_str(path: Path) -> str:
    """Decode a Python file as the interpreter would.

    Args:
        path: The file to read.

    Returns:
        The decoded text with its original line endings normalised to
        newlines by the decoder.
    """
    data_bytes = path.read_bytes()
    if path.suffix.lower() == ".ipynb":
        return join_notebook_cells_str(data_bytes.decode("utf-8"))
    readline = io.BytesIO(data_bytes).readline
    encoding_str, _ = tokenize.detect_encoding(readline)
    text_str = data_bytes.decode(encoding_str)
    return text_str.removeprefix("﻿")


def join_notebook_cells_str(text_str: str) -> str:
    """Join a notebook's code cells into one script text.

    The notebook is validated by RefacTrail's reader (Python nbformat 4,
    no duplicate keys or NaN constants). Magic and shell lines become
    comments, so they are neither run nor drawn.

    Args:
        text_str: The notebook JSON.

    Returns:
        The code cells in order, separated by blank lines; the last
        Markdown heading before a code cell becomes a "# %% Title"
        section marker above it.

    Warnings:
        Raises ValueError for notebooks RefacTrail refuses.
    """
    notebook_dict = read_notebook_dict(text_str.removeprefix("\ufeff"))
    cells_list = []
    heading_str = ""
    for index_int, cell_dict in enumerate(notebook_dict["cells"]):
        cell_str = read_cell_source_str(cell_dict, index_int)
        if cell_dict["cell_type"] == "markdown":
            heading_str = find_heading_str(cell_str) or heading_str
        elif cell_dict["cell_type"] == "code":
            if cell_str.lstrip().startswith("%%"):
                continue  # a cell magic: the whole cell is not Python
            marker_str = f"# %% {heading_str}\n" if heading_str else ""
            cells_list.append(marker_str + MAGIC_LINE_PATTERN.sub(
                r"\1# \2", cell_str))
            heading_str = ""
    return "\n\n".join(cells_list) + "\n"


def find_heading_str(markdown_str: str) -> str:
    """The last heading of a Markdown cell.

    Args:
        markdown_str: The cell text.

    Returns:
        The heading text without its # marks, or "".
    """
    headings_list = [match.group(1) for match in map(
        HEADING_PATTERN.match, markdown_str.splitlines()) if match]
    return headings_list[-1] if headings_list else ""


def collect_sections_list(text_str: str) -> list[tuple[int, str]]:
    """The section markers of a script.

    Args:
        text_str: The script text (notebooks already joined).

    Returns:
        (line, title) for every "# %% Title" line, in order.
    """
    return [(index_int, match.group(1)) for index_int, line_str in
            enumerate(text_str.splitlines(), start=1)
            if (match := SECTION_PATTERN.match(line_str))]


def parse_file(path: Path) -> ast.Module:
    """Parse a file into a syntax tree.

    Args:
        path: The file to parse.

    Returns:
        The module tree.

    Warnings:
        Raises SyntaxError for files Python cannot parse; callers report
        it instead of drawing a diagram.
    """
    return ast.parse(read_source_str(path), filename=str(path))


def describe_function(node: ast.FunctionDef | ast.AsyncFunctionDef,
                      module_str: str, owner_str: str = "") -> FunctionInfo:
    """Collect a function's summary, parameters and return annotation.

    Args:
        node: The def statement.
        module_str: The module it belongs to ("" for the script).
        owner_str: The class of a method, else "".

    Returns:
        The function's FunctionInfo.
    """
    summary_str = summarise_docstring_str(node)
    arguments = node.args
    parameters_list = []
    all_arguments_list = (arguments.posonlyargs + arguments.args
                          + arguments.kwonlyargs)
    for argument in all_arguments_list:
        annotation_str = (ast.unparse(argument.annotation)
                          if argument.annotation else "")
        parameters_list.append((argument.arg, annotation_str))
    returns_str = ast.unparse(node.returns) if node.returns else ""
    return FunctionInfo(node.name, summary_str, parameters_list,
                        returns_str, module_str, node.lineno, node.body,
                        owner_str)


def summarise_docstring_str(node: ast.AST) -> str:
    """The first paragraph of a docstring, on one line.

    Args:
        node: A def or class statement.

    Returns:
        The summary, or "".
    """
    docstring_str = ast.get_docstring(node) or ""
    return " ".join(docstring_str.strip().split("\n\n")[0].split())


def collect_classes(tree: ast.Module, module_str: str
                    ) -> dict[str, ClassInfo]:
    """Collect the top-level classes of a module with their methods.

    Args:
        tree: The module tree.
        module_str: The module name ("" for the script).

    Returns:
        ClassInfo by class name.
    """
    classes_dict = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods_dict = {
                child.name: describe_function(child, module_str, node.name)
                for child in node.body
                if isinstance(child, (ast.FunctionDef,
                                      ast.AsyncFunctionDef))}
            classes_dict[node.name] = ClassInfo(
                node.name, summarise_docstring_str(node), methods_dict,
                module_str)
    return classes_dict


def collect_functions(tree: ast.Module,
                      module_str: str) -> dict[str, FunctionInfo]:
    """Collect the top-level functions of a module.

    Args:
        tree: The module tree.
        module_str: The module name ("" for the script).

    Returns:
        FunctionInfo by function name.
    """
    functions_dict = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions_dict[node.name] = describe_function(node, module_str)
    return functions_dict


def collect_imports(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """Map every imported local name to its module and original name.

    Args:
        tree: The module tree; imports anywhere in it are collected.

    Returns:
        Local name -> (module, original name); the original name is ""
        for plain "import module" statements. Relative imports keep
        their leading dots.
    """
    imported_dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_str = alias.asname or alias.name.split(".")[0]
                module_str = alias.name if alias.asname else local_str
                imported_dict[local_str] = (module_str, "")
        elif isinstance(node, ast.ImportFrom):
            module_str = "." * node.level + (node.module or "")
            for alias in node.names:
                local_str = alias.asname or alias.name
                imported_dict[local_str] = (module_str, alias.name)
    return imported_dict


def find_module_file(folder: Path, module_str: str) -> Path | None:
    """Find a developed module's file next to the script.

    Args:
        folder: The script's folder.
        module_str: A module name such as "trip_utils", "pkg.helpers"
            or ".helpers".

    Returns:
        The module file, or None when it is not a local file (an
        installed or standard-library module).
    """
    relative_str = module_str.lstrip(".")
    if not relative_str:
        return None
    base_path = folder.joinpath(*relative_str.split("."))
    for candidate in (base_path.with_suffix(".py"), base_path / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def parse_module_tuple(module_path: Path, short_str: str
                       ) -> tuple[dict[str, FunctionInfo],
                                  dict[str, ClassInfo]]:
    """The functions and classes of a developed module.

    Args:
        module_path: The module file.
        short_str: Its file name, used for colours and the legend.

    Returns:
        (functions, classes); both empty when the file cannot be parsed,
        so it is treated like an installed module.
    """
    try:
        module_tree = parse_file(module_path)
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return {}, {}
    functions_dict = collect_functions(module_tree, short_str)
    classes_dict = collect_classes(module_tree, short_str)
    for function_info in [*functions_dict.values(), *(
            method for class_info in classes_dict.values()
            for method in class_info.methods.values())]:
        function_info.source_path = module_path
    return functions_dict, classes_dict


def add_developed_none(info: ScriptInfo, local_str: str,
                       original_str: str, short_str: str,
                       parsed_tuple: tuple[dict, dict]) -> None:
    """Record what one import brings in from a developed module.

    Args:
        info: The script (changed in place).
        local_str: The name the script uses.
        original_str: The imported name, or "" for "import module".
        short_str: The module's file name.
        parsed_tuple: The module's (functions, classes).

    Returns:
        None.
    """
    functions_dict, classes_dict = parsed_tuple
    if original_str in classes_dict:
        info.classes[local_str] = classes_dict[original_str]
    elif original_str:
        info.developed[local_str] = functions_dict.get(
            original_str) or FunctionInfo(original_str, module=short_str)
    else:
        info.developed_modules[local_str] = short_str
        for name_str, function_info in functions_dict.items():
            info.developed[f"{local_str}.{name_str}"] = function_info
        for name_str, class_info in classes_dict.items():
            info.classes[f"{local_str}.{name_str}"] = class_info


def load_script(path: Path) -> ScriptInfo:
    """Parse a script and the developed modules it imports from.

    Args:
        path: The script to read.

    Returns:
        Its ScriptInfo. Developed modules that fail to parse are
        treated like installed modules (no summaries or annotations).
    """
    text_str = read_source_str(path)
    tree = ast.parse(text_str, filename=str(path))
    info = ScriptInfo(path, tree, collect_functions(tree, ""),
                      collect_imports(tree))
    info.sections = collect_sections_list(text_str)
    info.classes.update(collect_classes(tree, ""))
    parsed_dict: dict[str, tuple[dict, dict]] = {}
    for local_str, (module_str, original_str) in info.imported.items():
        module_path = find_module_file(path.parent, module_str)
        if module_path is None:
            continue
        short_str = module_str.lstrip(".").split(".")[-1] + ".py"
        if module_str not in parsed_dict:
            parsed_dict[module_str] = parse_module_tuple(module_path,
                                                         short_str)
        add_developed_none(info, local_str, original_str, short_str,
                           parsed_dict[module_str])
    return info
