"""Draw a project overview: one block per script, module or notebook.

``flowblueprint FOLDER`` reads every Python file and notebook below a
folder without running them and draws which files use which: an arrow
from a file to each project file it imports. Each block names the file,
says whether it is an entry point, a notebook or a module, summarises
it (module docstring, else the steps it runs or the functions it
defines) and lists the files, databases and storage it reads and
writes. Entry points sit at the top and the modules they use below
them, so the page reads from what you run down to what it relies on.
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path

from flowblueprint import describe
from flowblueprint.flow import MAIN_GUARD_PATTERN, FlowBuilder, build_flow
from flowblueprint.model import Source, Step
from flowblueprint.source import (
    ScriptInfo, collect_imports, load_script, parse_file,
    summarise_docstring_str)

SKIPPED_DIRS_FROZENSET = frozenset((
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__", "build",
    "dist", "node_modules", ".tox", ".nox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".ipynb_checkpoints", "site-packages", ".eggs"))
TEST_DIRS_FROZENSET = frozenset(("tests", "test", "testing"))
ENTRY_KIND = "entry point"
NOTEBOOK_KIND = "notebook"
MODULE_KIND = "module"
PACKAGE_KIND = "package"
MAX_NAMES_INT = 3
DATA_EXTENSIONS_FROZENSET = frozenset((
    "csv", "tsv", "txt", "json", "jsonl", "ndjson", "parquet", "pq",
    "feather", "arrow", "orc", "avro", "xlsx", "xls", "xlsm", "ods", "yaml",
    "yml", "toml", "ini", "cfg", "conf", "xml", "html", "htm", "pkl",
    "pickle", "joblib", "npy", "npz", "h5", "hdf5", "nc", "mat", "db",
    "sqlite", "sqlite3", "sql", "png", "jpg", "jpeg", "svg", "pdf", "log",
    "md", "zip", "gz", "bz2", "xz", "tar", "pt", "pth", "onnx", "bin"))


@dataclass
class FileInfo:
    """What the overview shows about one project file.

    Args:
        path: The file, relative to the project folder.
        module: Its dotted module name ("" for notebooks).
        kind: ENTRY_KIND, NOTEBOOK_KIND, MODULE_KIND or PACKAGE_KIND.
        summary: One sentence about the file.
        functions_count: Top-level functions it defines.
        classes_count: Top-level classes it defines.
        reads: Files, databases and storage it reads.
        writes: Those it writes.
        imports: (module, level, imported names) of each import.
    """

    path: Path
    module: str
    kind: str
    summary: str = ""
    functions_count: int = 0
    classes_count: int = 0
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    imports: list[tuple[str, int, list[str]]] = field(default_factory=list)


@dataclass
class Project:
    """The files of a project and the imports between them.

    Args:
        name: The folder name, shown as the diagram title.
        files: The files, in path order.
        edges: (importer index, imported index) pairs.
        notes: Files left out, with reasons.
    """

    name: str
    files: list[FileInfo] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check_test_path_bool(relative: Path) -> bool:
    """Whether a path is a test file or lies in a test folder.

    Args:
        relative: The path relative to the project folder.

    Returns:
        True for test_*.py, *_test.py, conftest.py and files below a
        tests, test or testing folder.
    """
    name_str = relative.name
    return (any(part in TEST_DIRS_FROZENSET for part in relative.parts[:-1])
            or name_str.startswith("test_") or name_str == "conftest.py"
            or name_str.endswith("_test.py"))


def discover_files_list(folder: Path, include_tests: bool) -> list[Path]:
    """Find the project's Python files and notebooks.

    Args:
        folder: The project folder.
        include_tests: Keep test files and test folders.

    Returns:
        Paths relative to the folder, sorted. Hidden folders, virtual
        environments, caches and build output are skipped.
    """
    found_list = []
    for path in folder.rglob("*"):
        relative = path.relative_to(folder)
        if any(part in SKIPPED_DIRS_FROZENSET or part.startswith(".")
               for part in relative.parts[:-1]):
            continue
        if path.suffix.lower() not in (".py", ".ipynb") or not path.is_file():
            continue
        if not include_tests and check_test_path_bool(relative):
            continue
        found_list.append(relative)
    return sorted(found_list, key=lambda relative: relative.as_posix())


def find_package_prefix_list(folder: Path) -> list[str]:
    """The package path of a folder that is itself inside packages.

    Args:
        folder: The project folder.

    Returns:
        ["pkg", "sub"] for a folder pkg/sub where both hold an
        __init__.py, so its files are named as they import each other;
        [] for an ordinary project folder.
    """
    prefix_list: list[str] = []
    current = folder.resolve()
    while (current / "__init__.py").is_file() and current.name:
        prefix_list.insert(0, current.name)
        current = current.parent
    return prefix_list


def make_module_name_str(relative: Path, prefix_list: list[str]) -> str:
    """The dotted module name of a project file.

    Args:
        relative: The path relative to the project folder.
        prefix_list: The folder's own package path (usually []).

    Returns:
        "pkg.helpers" for pkg/helpers.py, "pkg" for pkg/__init__.py and
        "" for notebooks.
    """
    if relative.suffix.lower() == ".ipynb":
        return ""
    parts_list = prefix_list + list(relative.with_suffix("").parts)
    if parts_list and parts_list[-1] == "__init__":
        parts_list.pop()
    return ".".join(parts_list)


def check_entry_point_bool(tree: ast.Module) -> bool:
    """Whether a module does something when run, not only defines.

    Args:
        tree: The module tree.

    Returns:
        True with a main guard or top-level statements other than
        definitions, imports, assignments and the docstring.
    """
    passive_tuple = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                     ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign,
                     ast.TypeAlias, ast.Pass)
    for node in tree.body:
        if (isinstance(node, ast.If)
                and MAIN_GUARD_PATTERN.match(ast.unparse(node.test))):
            return True
        if isinstance(node, ast.Expr) and isinstance(node.value,
                                                     ast.Constant):
            continue
        if not isinstance(node, passive_tuple + (ast.If, ast.Try)):
            return True
    return False


def collect_raw_imports_list(tree: ast.Module
                             ) -> list[tuple[str, int, list[str]]]:
    """Every import of a module, unresolved.

    Args:
        tree: The module tree; imports anywhere in it count.

    Returns:
        (module, level, names) per statement; names are [] for plain
        "import a.b" statements.
    """
    imports_list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports_list.extend((alias.name, 0, []) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports_list.append((node.module or "", node.level,
                                 [alias.name for alias in node.names]))
    return imports_list


def check_location_label_bool(label_str: str) -> bool:
    """Whether a source label names a location rather than a variable.

    Args:
        label_str: The label FlowBlueprint built for a file or table.

    Returns:
        True for file names with a data extension, and for paths and
        URLs written without spaces (not "folder / name" expressions).
    """
    if any(mark_str in label_str for mark_str in ("'", '"')):
        return False  # a bytes or string expression, not a location
    if " " not in label_str and any(
            mark_str in label_str for mark_str in ("/", "\\")):
        return True
    extension_str = label_str.rsplit(".", 1)[-1].lower()
    return "." in label_str and extension_str in DATA_EXTENSIONS_FROZENSET


def make_location_label_str(label_str: str) -> str:
    """A readable label for a location.

    Args:
        label_str: A label accepted by check_location_label_bool.

    Returns:
        "*.parquet" for a bare extension (the rest of the name is
        computed, as in f"{station}.parquet"); the label otherwise.
    """
    return "*" + label_str if label_str.startswith(".") else label_str


def collect_sources_tuple(path: Path, tree: ast.Module
                          ) -> tuple[list[str], list[str]]:
    """The locations a file reads and writes.

    Args:
        path: The file.
        tree: Its tree.

    Returns:
        (reads, writes): unique labels in order of appearance; labels
        that are only variable names are left out.
    """
    builder = FlowBuilder(ScriptInfo(path, tree, {}, collect_imports(tree)))
    reads_list: list[str] = []
    writes_list: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        source: Source | None = builder.find_io_source(node)
        if source is None or not check_location_label_bool(source.label):
            continue
        target_list = writes_list if source.is_output else reads_list
        label_str = make_location_label_str(source.label)
        if label_str not in target_list:
            target_list.append(label_str)
    return reads_list, writes_list


def name_some_str(names_list: list[str]) -> str:
    """Join up to MAX_NAMES_INT names, counting the rest.

    Args:
        names_list: Names in order.

    Returns:
        "a, b and c" or "a, b, c and 2 more".
    """
    if len(names_list) <= MAX_NAMES_INT:
        return describe.join_names_str(names_list)
    shown_list = names_list[:MAX_NAMES_INT]
    return (", ".join(shown_list)
            + f" and {len(names_list) - MAX_NAMES_INT} more")


def summarise_entry_str(path: Path) -> str:
    """A sentence naming the steps an entry point runs.

    Args:
        path: The entry point script or notebook.

    Returns:
        "Runs a, b and c." from its flow's top-level titled steps, or
        "" when it has none or cannot be read.
    """
    try:
        flow = build_flow(load_script(path))
    except (OSError, SyntaxError, ValueError, RecursionError):
        return ""
    titles_list: list[str] = []
    for item in flow.items:
        if isinstance(item, Step) and item.title and (
                item.title not in titles_list):
            titles_list.append(item.title)
    if not titles_list:
        return ""
    return f"Runs {name_some_str(titles_list)}."


def summarise_module_str(tree: ast.Module) -> str:
    """A sentence naming what a module defines.

    Args:
        tree: The module tree.

    Returns:
        "Provides a, b and c." for its public top-level functions and
        classes, or "" when it defines none.
    """
    names_list = [node.name for node in tree.body
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef))
                  and not node.name.startswith("_")]
    if not names_list:
        return ""
    return f"Provides {name_some_str(names_list)}."


def read_file_info(folder: Path, relative: Path,
                   prefix_list: list[str]) -> FileInfo:
    """Read one project file.

    Args:
        folder: The project folder.
        relative: The file, relative to the folder.
        prefix_list: The folder's own package path (usually []).

    Returns:
        Its FileInfo.

    Warnings:
        Raises SyntaxError, ValueError or OSError for files that
        cannot be read; the caller notes and skips them.
    """
    path = folder / relative
    tree = parse_file(path)
    module_str = make_module_name_str(relative, prefix_list)
    is_notebook = relative.suffix.lower() == ".ipynb"
    if is_notebook:
        kind_str = NOTEBOOK_KIND
    elif check_entry_point_bool(tree):
        kind_str = ENTRY_KIND
    else:
        kind_str = (PACKAGE_KIND if relative.name == "__init__.py"
                    else MODULE_KIND)
    summary_str = summarise_docstring_str(tree)
    if not summary_str and kind_str in (ENTRY_KIND, NOTEBOOK_KIND):
        summary_str = summarise_entry_str(path)
    if not summary_str:
        summary_str = summarise_module_str(tree)
    reads_list, writes_list = collect_sources_tuple(path, tree)
    return FileInfo(
        relative, module_str, kind_str, summary_str,
        sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in tree.body),
        sum(isinstance(node, ast.ClassDef) for node in tree.body),
        reads_list, writes_list, collect_raw_imports_list(tree))


def list_import_bases_list(info: FileInfo, module_str: str,
                           level_int: int) -> list[tuple[list[str],
                                                         list[str]]]:
    """Where an import may point, most specific first.

    Args:
        info: The importing file.
        module_str: The imported module, without leading dots.
        level_int: The number of leading dots.

    Returns:
        (package prefix, module parts) pairs: for relative imports the
        one package they start from; for absolute imports each of the
        importer's package folders (script folders and src layouts),
        then the project root.
    """
    own_parts_list = info.module.split(".") if info.module else []
    package_parts_list = (own_parts_list if info.kind == PACKAGE_KIND
                          else own_parts_list[:-1])
    module_parts_list = module_str.split(".") if module_str else []
    if level_int:
        keep_int = len(package_parts_list) - (level_int - 1)
        if keep_int < 0:
            return []
        return [(package_parts_list[:keep_int], module_parts_list)]
    return [(package_parts_list[:end_int], module_parts_list)
            for end_int in range(len(package_parts_list), -1, -1)]


def match_import_list(index_dict: dict[str, int], prefix_list: list[str],
                      module_parts_list: list[str], names_list: list[str]
                      ) -> list[int]:
    """The project files one import refers to from one package.

    Args:
        index_dict: Module name -> file index.
        prefix_list: The package the import is looked up in.
        module_parts_list: The imported module's parts.
        names_list: Names imported from it ([] for "import a.b").

    Returns:
        The imported submodules when any are project files, else the
        deepest project module along the imported module (never a
        package above it); [] when none.
    """
    full_list = prefix_list + module_parts_list
    submodules_list = [index_dict[".".join(full_list + [name_str])]
                       for name_str in names_list
                       if ".".join(full_list + [name_str]) in index_dict]
    if submodules_list:
        return submodules_list
    lowest_int = len(prefix_list) + (1 if module_parts_list else 0)
    for end_int in range(len(full_list), lowest_int - 1, -1):
        found_int = index_dict.get(".".join(full_list[:end_int]))
        if found_int is not None and end_int:
            return [found_int]
    return []


def resolve_edges_list(files_list: list[FileInfo]) -> list[tuple[int, int]]:
    """The imports between project files.

    Args:
        files_list: The project files.

    Returns:
        Unique (importer, imported) index pairs, in file order.
    """
    index_dict = {info.module: index_int
                  for index_int, info in enumerate(files_list) if info.module}
    for index_int, info in enumerate(files_list):
        if info.module.startswith("src."):
            index_dict.setdefault(info.module.removeprefix("src."),
                                  index_int)
    edges_list: list[tuple[int, int]] = []
    for index_int, info in enumerate(files_list):
        for module_str, level_int, names_list in info.imports:
            for prefix_list, parts_list in list_import_bases_list(
                    info, module_str, level_int):
                targets_list = match_import_list(index_dict, prefix_list,
                                                 parts_list, names_list)
                for target_int in targets_list:
                    if target_int != index_int and (
                            (index_int, target_int) not in edges_list):
                        edges_list.append((index_int, target_int))
                if targets_list:
                    break
    return edges_list


def load_project(folder: Path, include_tests: bool = False) -> Project:
    """Read a project folder.

    Args:
        folder: The folder.
        include_tests: Keep test files and test folders.

    Returns:
        The Project. Files that cannot be read are left out with a
        note.
    """
    project = Project(folder.resolve().name)
    prefix_list = find_package_prefix_list(folder)
    for relative in discover_files_list(folder, include_tests):
        try:
            project.files.append(read_file_info(folder, relative,
                                                prefix_list))
        except (OSError, SyntaxError, ValueError, RecursionError) as error:
            project.notes.append(f"{relative.as_posix()}: not drawn: "
                                 f"{type(error).__name__}: {error}")
    project.edges = resolve_edges_list(project.files)
    return project
