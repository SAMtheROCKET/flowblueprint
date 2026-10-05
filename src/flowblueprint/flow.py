"""Turn a script's entry point into an ordered flow of steps.

The entry point is the body of the ``if __name__ == "__main__":`` block
(or of ``main()`` when that block only calls it), else ``main()``, else
the module-level statements. Calls to functions of the script or of
developed (local) modules become titled blocks; file, database and
storage reads and writes get their own shapes; plotting statements
become one plot block; other statements are grouped into short plain
blocks. Statements that are not drawn are reported as notes.
"""

import ast
from pathlib import PurePath
import re

from flowblueprint import describe, dtypes
from flowblueprint.model import (
    DATA_KIND, DATABASE_KIND, DOCUMENT_KIND, PLOT_KIND, PROCESS_KIND,
    STORAGE_KIND, Branch, Flow, Item, Loop, Note, Port, Source, Step)
from flowblueprint.source import FunctionInfo, ScriptInfo

MAX_TEXT_LENGTH_INT = 60

READ_NAMES_FROZENSET = frozenset((
    "read_csv", "read_parquet", "read_excel", "read_json", "read_feather",
    "read_pickle", "read_table", "read_hdf", "read_sql", "read_sql_query",
    "read_sql_table", "read_file", "load", "loadtxt", "genfromtxt",
    "read_text", "read_bytes", "imread", "safe_load", "read_orc"))
WRITE_NAMES_FROZENSET = frozenset((
    "to_csv", "to_parquet", "to_excel", "to_json", "to_pickle",
    "to_feather", "to_sql", "to_file", "dump", "save", "savez",
    "savetxt", "write_text", "write_bytes", "imwrite", "savefig",
    "safe_dump", "to_orc"))
DATABASE_NAMES_FROZENSET = frozenset((
    "read_sql", "read_sql_query", "read_sql_table", "to_sql", "connect",
    "create_engine"))
PLOT_MODULE_PREFIXES_TUPLE = ("matplotlib", "seaborn", "plotly", "bokeh",
                              "altair")
PLOT_METHODS_FROZENSET = frozenset((
    "plot", "hist", "scatter", "bar", "barh", "boxplot", "imshow",
    "set_title", "set_xlabel", "set_ylabel", "legend", "savefig", "show",
    "subplots", "figure", "tight_layout", "heatmap", "lineplot"))
STORAGE_PATTERN = re.compile(r"^(s3|gs|gcs|abfs|az|hdfs)://|^\\\\")
MAIN_GUARD_PATTERN = re.compile(
    r"""^__name__\s*==\s*['"]__main__['"]$""")


def shorten_str(text_str: str) -> str:
    """Shorten text to MAX_TEXT_LENGTH_INT characters.

    Args:
        text_str: The text.

    Returns:
        The text, cut with "..." when longer than the limit.
    """
    text_str = " ".join(text_str.split())
    if len(text_str) <= MAX_TEXT_LENGTH_INT:
        return text_str
    return text_str[:MAX_TEXT_LENGTH_INT - 3].rstrip() + "..."


def strip_docstring_list(body_list: list[ast.stmt]) -> list[ast.stmt]:
    """Drop a leading docstring from a body.

    Args:
        body_list: Statements.

    Returns:
        The statements without a leading string expression.
    """
    if (body_list and isinstance(body_list[0], ast.Expr)
            and isinstance(body_list[0].value, ast.Constant)
            and isinstance(body_list[0].value.value, str)):
        return body_list[1:]
    return body_list


def find_function_node(tree: ast.Module, name_str: str
                       ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Find a top-level function definition by name.

    Args:
        tree: The module tree.
        name_str: The function name.

    Returns:
        The last definition with that name, or None.
    """
    found_node = None
    for node in tree.body:
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name_str):
            found_node = node
    return found_node


def check_only_calls_main_bool(body_list: list[ast.stmt]) -> bool:
    """Whether a main-guard body only calls main().

    Args:
        body_list: The guard body.

    Returns:
        True for "main()", "sys.exit(main())" or "raise
        SystemExit(main())" alone.
    """
    if len(body_list) != 1:
        return False
    statement = body_list[0]
    value = (statement.value if isinstance(statement, ast.Expr)
             else statement.exc if isinstance(statement, ast.Raise)
             else None)
    while isinstance(value, ast.Call) and value.args and not (
            isinstance(value.func, ast.Name) and value.func.id == "main"):
        value = value.args[0]
    return (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id == "main")


def find_entry_statements_list(tree: ast.Module) -> list[ast.stmt]:
    """The statements the script runs as its main flow.

    Args:
        tree: The script's tree.

    Returns:
        The main-guard body, main()'s body or the module-level
        statements, as described in the module docstring.
    """
    guard_body_list = None
    for node in tree.body:
        if (isinstance(node, ast.If)
                and MAIN_GUARD_PATTERN.match(ast.unparse(node.test))):
            guard_body_list = node.body
    main_node = find_function_node(tree, "main")
    if main_node and (guard_body_list is None
                      or check_only_calls_main_bool(guard_body_list)):
        return strip_docstring_list(main_node.body)
    if guard_body_list is not None:
        return guard_body_list
    skipped_tuple = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                     ast.Import, ast.ImportFrom)
    return [node for node in strip_docstring_list(tree.body)
            if not isinstance(node, skipped_tuple)]


def collect_constants_dict(tree: ast.Module) -> dict[str, str]:
    """Module-level names assigned a string literal.

    Args:
        tree: The script's tree.

    Returns:
        Name -> string value, used to label file shapes.
    """
    constants_dict = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            constants_dict[node.targets[0].id] = node.value.value
    return constants_dict


class FlowBuilder:
    """Builds the Flow of one script; see build_flow."""

    def __init__(self, info: ScriptInfo) -> None:
        """Prepare the builder.

        Args:
            info: The parsed script.
        """
        self.info = info
        self.constants_dict = collect_constants_dict(info.tree)
        self.env_dict: dict[str, str] = {}
        self.handles_dict: dict[str, tuple[str, bool]] = {}
        self.used_handles_set: set[str] = set()
        self.modules_list: list[str] = []
        self.notes_list: list[Note] = []
        for node in info.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                self.record_assignment_none(node)

    # ----- variables and their types -----

    def record_assignment_none(self, statement: ast.Assign | ast.AnnAssign
                          ) -> None:
        """Record the types a plain assignment gives its targets.

        Args:
            statement: The assignment.

        Returns:
            None.
        """
        if isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name):
                self.env_dict[statement.target.id] = ast.unparse(
                    statement.annotation)
            return
        if statement.value is None:
            return
        value_dtype_str = dtypes.infer_value_dtype_str(statement.value)
        if isinstance(statement.value, ast.Call):
            called_info = self.resolve_function(statement.value)
            if called_info is not None:
                value_dtype_str = dtypes.pick_known_dtype_str(
                    called_info.returns, value_dtype_str)
        for name_str in describe.list_target_names_list(statement.targets):
            self.env_dict[name_str] = dtypes.pick_known_dtype_str(
                value_dtype_str, self.env_dict.get(name_str, ""),
                dtypes.infer_name_dtype_str(name_str))

    def make_port(self, expression: ast.expr,
                  annotation_str: str = "") -> Port:
        """A port for an expression passed to or returned by a step.

        Args:
            expression: The expression as written.
            annotation_str: The parameter or return annotation, if any.

        Returns:
            The Port with the best-evidenced type.
        """
        name_str = shorten_str(ast.unparse(expression))
        return Port(name_str, dtypes.pick_known_dtype_str(
            self.env_dict.get(name_str, ""), annotation_str,
            dtypes.infer_value_dtype_str(expression),
            dtypes.infer_name_dtype_str(name_str)))

    def output_ports_list(self, targets_list: list[ast.expr],
                          returns_str: str) -> list[Port]:
        """Ports for assignment targets, typed from a return annotation.

        Args:
            targets_list: The assignment targets (may be empty).
            returns_str: The called function's return annotation.

        Returns:
            One Port per assigned name; the types are also recorded.
        """
        names_list = describe.list_target_names_list(targets_list)
        if len(names_list) > 1:
            parts_list = dtypes.split_tuple_annotation_list(
                returns_str, len(names_list))
        else:
            parts_list = [returns_str] * len(names_list)
        ports_list = []
        for name_str, part_str in zip(names_list, parts_list):
            dtype_str = dtypes.pick_known_dtype_str(
                part_str, dtypes.infer_name_dtype_str(name_str))
            self.env_dict[name_str] = dtype_str
            ports_list.append(Port(name_str, dtype_str))
        return ports_list

    # ----- what a call is -----

    def resolve_function(self, call: ast.Call) -> FunctionInfo | None:
        """The script or developed function a call runs, if any.

        Args:
            call: The call.

        Returns:
            Its FunctionInfo, or None for library and unknown calls.
        """
        name_str = dtypes.read_called_name_str(call.func)
        if name_str in self.info.functions:
            return self.info.functions[name_str]
        if name_str in self.info.developed:
            return self.info.developed[name_str]
        if name_str in self.info.classes:
            return self.describe_constructor(name_str)
        class_str, method_str = "", ""
        if "." in name_str and not name_str.startswith("."):
            receiver_str, method_str = name_str.rsplit(".", 1)
            class_str = (receiver_str if receiver_str in self.info.classes
                         else self.env_dict.get(receiver_str, ""))
        elif isinstance(call.func, ast.Attribute) and isinstance(
                call.func.value, ast.Call):
            inner_info = self.resolve_function(call.func.value)
            class_str = inner_info.returns if inner_info else ""
            method_str = call.func.attr
        class_info = self.info.classes.get(class_str)
        return class_info.methods.get(method_str) if class_info else None

    def describe_constructor(self, class_str: str) -> FunctionInfo:
        """A FunctionInfo for creating an instance of a known class.

        Args:
            class_str: The class name as the script uses it.

        Returns:
            Its __init__ parameters (without self), the class docstring
            summary and the class as the result type.
        """
        class_info = self.info.classes[class_str]
        init_info = class_info.methods.get("__init__")
        parameters_list = init_info.parameters[1:] if init_info else []
        summary_str = (f"Create the {class_info.name}: {class_info.summary}"
                       if class_info.summary
                       else f"Create the {class_info.name}")
        return FunctionInfo(class_info.name, summary_str, parameters_list,
                            class_str, class_info.module)

    def find_inline_target(self, statements_list: list[ast.stmt]
                           ) -> tuple[int, FunctionInfo] | None:
        """The single script function the entry point hands over to.

        Args:
            statements_list: The entry statements.

        Returns:
            (statement index, function) when exactly one call in the
            entry runs a script function or method (constructors aside)
            with at least three statements of its own; else None.
        """
        found_list = []
        for index_int, statement in enumerate(statements_list):
            for call in (node for node in ast.walk(statement)
                         if isinstance(node, ast.Call)):
                function_info = self.resolve_function(call)
                if function_info is None or function_info.name in (
                        self.info.classes):
                    continue
                found_list.append((index_int, function_info))
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                self.record_assignment_none(statement)
        if len(found_list) != 1:
            return None
        index_int, function_info = found_list[0]
        body_list = strip_docstring_list(function_info.body)
        if function_info.module or len(body_list) < 3:
            return None
        return index_int, function_info

    def build_entry_items(self, statements_list: list[ast.stmt]
                          ) -> list[Item]:
        """Build the main flow, expanding a single hand-over call.

        Args:
            statements_list: The entry statements.

        Returns:
            The items. When the entry only hands over to one script
            function or method (for example "Pipeline(config).run()"),
            that function's body is drawn in its place, with "self"
            typed as its class.
        """
        saved_env_dict = dict(self.env_dict)
        target_tuple = self.find_inline_target(statements_list)
        self.env_dict = saved_env_dict
        if target_tuple is None:
            return self.build_items(statements_list)
        index_int, function_info = target_tuple
        items_list = self.build_items(statements_list[:index_int])
        if function_info.owner_class:
            self.env_dict["self"] = function_info.owner_class
        for name_str, annotation_str in function_info.parameters:
            if annotation_str and name_str != "self":
                self.env_dict[name_str] = annotation_str
        items_list += self.build_items(strip_docstring_list(
            function_info.body))
        return items_list + self.build_items(statements_list[index_int + 1:])

    def is_plot_call(self, call: ast.Call) -> bool:
        """Whether a call draws or saves a figure.

        Args:
            call: The call.

        Returns:
            True for calls into plotting libraries and plot methods.
        """
        name_str = dtypes.read_called_name_str(call.func)
        root_str = name_str.split(".")[0]
        module_str = self.info.imported.get(root_str, ("", ""))[0]
        if module_str.startswith(PLOT_MODULE_PREFIXES_TUPLE):
            return True
        return ("." in name_str
                and name_str.split(".")[-1] in PLOT_METHODS_FROZENSET
                and name_str.split(".")[-1] not in ("show", "legend")
                or name_str.endswith((".plot", ".hist")))

    def label_str(self, expression: ast.expr) -> str:
        """The short label of a file location expression.

        Args:
            expression: A path, file name, handle or URL expression.

        Returns:
            The file name for literal and constant paths; the
            expression text otherwise.
        """
        if isinstance(expression, ast.Name):
            if expression.id in self.handles_dict:
                self.used_handles_set.add(expression.id)
                return self.handles_dict[expression.id][0]
            if expression.id in self.constants_dict:
                return extract_file_name_str(
                    self.constants_dict[expression.id])
        strings_list = [node.value for node in ast.walk(expression)
                        if isinstance(node, ast.Constant)
                        and isinstance(node.value, str)]
        if strings_list:
            return extract_file_name_str(strings_list[-1])
        return shorten_str(ast.unparse(expression))

    def find_io_source(self, call: ast.Call) -> Source | None:
        """The file, database or storage a call reads or writes.

        Args:
            call: The call.

        Returns:
            A Source, or None when the call does no recognised I/O.
        """
        name_str = dtypes.read_called_name_str(call.func)
        short_str = name_str.split(".")[-1]
        receiver_str = name_str.rsplit(".", 1)[0] if "." in name_str else ""
        if receiver_str in self.handles_dict and short_str in (
                "read", "readlines", "write", "writelines"):
            self.used_handles_set.add(receiver_str)
            label_str, is_output = self.handles_dict[receiver_str]
            return Source(DATA_KIND, label_str, is_output)
        is_read = short_str in READ_NAMES_FROZENSET or (
            short_str == "read" and check_string_argument_bool(call))
        is_write = short_str in WRITE_NAMES_FROZENSET
        is_connect = short_str in ("connect", "create_engine")
        if not (is_read or is_write or is_connect):
            return None
        location = self.find_location_argument(call, short_str, is_write)
        label_str = self.label_str(location) if location else short_str
        if short_str == "savefig":
            return Source(DOCUMENT_KIND, label_str, True)
        if short_str in DATABASE_NAMES_FROZENSET:
            return Source(DATABASE_KIND, label_str, is_write)
        texts_list = [node.value for node in ast.walk(location)
                      if isinstance(node, ast.Constant)
                      and isinstance(node.value, str)] if location else []
        if isinstance(location, ast.Name):
            texts_list.append(self.constants_dict.get(location.id, ""))
        is_storage = any(STORAGE_PATTERN.match(text_str)
                         for text_str in texts_list)
        return Source(STORAGE_KIND if is_storage else DATA_KIND, label_str,
                      is_write)

    def find_location_argument(self, call: ast.Call, short_str: str,
                               is_write: bool) -> ast.expr | None:
        """The argument naming where a call reads or writes.

        Args:
            call: The call.
            short_str: The called name's last part.
            is_write: Whether the call writes.

        Returns:
            The location expression, or None (for example for
            "path.read_text()", whose receiver is the location).
        """
        arguments_list = list(call.args)
        if short_str in ("dump", "safe_dump") and len(arguments_list) > 1:
            return arguments_list[1]
        if short_str in ("save", "savez", "savetxt", "imwrite"):
            return arguments_list[0] if arguments_list else None
        if arguments_list:
            return arguments_list[0]
        if isinstance(call.func, ast.Attribute) and short_str in (
                "read_text", "read_bytes", "write_text", "write_bytes"):
            return call.func.value
        return None

    # ----- statements to items -----

    def build_items(self, statements_list: list[ast.stmt]) -> list[Item]:
        """Turn statements into steps, loops and branches.

        Args:
            statements_list: Statements run in order.

        Returns:
            The items, with plain and plot statements grouped.
        """
        items_list: list[Item] = []
        plain_list: list[ast.stmt] = []
        plot_list: list[ast.stmt] = []
        for statement in statements_list:
            kind_str = self.classify_statement_str(statement)
            if kind_str == "plain":
                self.flush_plot_none(plot_list, items_list)
                plain_list.append(statement)
                continue
            if kind_str == "plot":
                self.flush_plain_none(plain_list, items_list)
                plot_list.append(statement)
                continue
            self.flush_plain_none(plain_list, items_list)
            self.flush_plot_none(plot_list, items_list)
            if kind_str != "skip":
                items_list.extend(self.build_statement(statement))
        self.flush_plain_none(plain_list, items_list)
        self.flush_plot_none(plot_list, items_list)
        return items_list

    def classify_statement_str(self, statement: ast.stmt) -> str:
        """Classify a statement for grouping.

        Args:
            statement: The statement.

        Returns:
            "skip", "plain", "plot" or "own" (drawn on its own).
        """
        if isinstance(statement, (ast.Pass, ast.Import, ast.ImportFrom,
                                  ast.Global, ast.Nonlocal)):
            return "skip"
        if not isinstance(statement, (ast.Assign, ast.AnnAssign,
                                      ast.AugAssign, ast.Expr,
                                      ast.Delete)):
            return "own"
        if (isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)):
            return "skip"
        calls_list = [node for node in ast.walk(statement)
                      if isinstance(node, ast.Call)]
        value = getattr(statement, "value", None)
        if isinstance(value, ast.Call) and any(
                self.resolve_function(ast.Call(pipe_call.args[0], [], []))
                for pipe_call in list_pipe_chain_list(value)):
            return "own"
        if any(self.resolve_function(call) or self.check_io_bool(call)
               for call in calls_list if not self.is_plot_call(call)):
            return "own"
        if any(self.is_plot_call(call) for call in calls_list):
            return "plot"
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            self.record_assignment_none(statement)
        return "plain"

    def check_io_bool(self, call: ast.Call) -> bool:
        """Whether a call does I/O, without marking handles as used.

        Args:
            call: The call.

        Returns:
            True when io_source finds a location.
        """
        used_set = set(self.used_handles_set)
        found = self.find_io_source(call) is not None
        self.used_handles_set = used_set
        return found

    def flush_plain_none(self, plain_list: list[ast.stmt],
                         items_list: list[Item]) -> None:
        """Emit pending plain statements as one step and clear them.

        Args:
            plain_list: Pending plain statements (cleared).
            items_list: Where the step goes.

        Returns:
            None.
        """
        if plain_list:
            items_list.append(Step(
                PROCESS_KIND, "", describe.describe_group_str(plain_list),
                line=plain_list[0].lineno))
            plain_list.clear()

    def flush_plot_none(self, plot_list: list[ast.stmt],
                        items_list: list[Item]) -> None:
        """Emit pending plotting statements as one plot step.

        Args:
            plot_list: Pending plotting statements (cleared).
            items_list: Where the step goes.

        Returns:
            None.
        """
        if not plot_list:
            return
        inputs_list: list[Port] = []
        sources_list: list[Source] = []
        title_str = ""
        for statement in plot_list:
            for call in (node for node in ast.walk(statement)
                         if isinstance(node, ast.Call)):
                short_str = dtypes.read_called_name_str(
                    call.func).split(".")[-1]
                if short_str in ("title", "set_title", "suptitle") and (
                        call.args and isinstance(call.args[0], ast.Constant)):
                    title_str = title_str or str(call.args[0].value)
                if short_str == "savefig":
                    sources_list.append(self.find_io_source(call))
                self.add_data_inputs_none(call, inputs_list)
        subject_str = title_str or describe.join_names_str(
            [port.name for port in inputs_list]) or "the figure"
        items_list.append(Step(
            PLOT_KIND, "", describe.make_sentence_str(f"plot {subject_str}"),
            inputs_list, [], line=plot_list[0].lineno,
            sources=[source for source in sources_list if source]))
        plot_list.clear()

    def add_data_inputs_none(self, call: ast.Call,
                             inputs_list: list[Port]) -> None:
        """Add the plotted variables of a call as plot inputs.

        Args:
            call: A plotting call.
            inputs_list: The plot's inputs so far (extended in place).

        Returns:
            None.
        """
        candidates_list = list(call.args) + [
            keyword.value for keyword in call.keywords
            if keyword.arg in ("data", "x", "y", "df")]
        if isinstance(call.func, ast.Attribute) and isinstance(
                call.func.value, ast.Name) and call.func.attr in (
                    "plot", "hist", "scatter", "bar", "boxplot"):
            candidates_list.insert(0, call.func.value)
        known_set = {port.name for port in inputs_list}
        for candidate in candidates_list:
            if (isinstance(candidate, ast.Name)
                    and candidate.id not in self.info.imported
                    and candidate.id not in known_set
                    and len(inputs_list) < 4):
                inputs_list.append(self.make_port(candidate))
                known_set.add(candidate.id)

    def build_statement(self, statement: ast.stmt) -> list[Item]:
        """Build the items of a statement drawn on its own.

        Args:
            statement: A control-flow statement or a statement with a
                local call or I/O.

        Returns:
            The statement's items (possibly none, with a note).
        """
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            self.note_else_none(statement, "for")
            header_str = (f"for {ast.unparse(statement.target)} in "
                          f"{ast.unparse(statement.iter)}")
            return [Loop(shorten_str(header_str),
                         self.build_items(statement.body), statement.lineno)]
        if isinstance(statement, ast.While):
            self.note_else_none(statement, "while")
            return [Loop(shorten_str(f"while {ast.unparse(statement.test)}"),
                         self.build_items(statement.body), statement.lineno)]
        if isinstance(statement, ast.If):
            yes_list, yes_jump_str = split_jump_tuple(statement.body)
            no_list, no_jump_str = split_jump_tuple(statement.orelse)
            return [Branch(shorten_str(ast.unparse(statement.test)) + "?",
                           self.build_items(yes_list),
                           self.build_items(no_list), statement.lineno,
                           yes_jump_str, no_jump_str)]
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            return self.build_with(statement)
        if isinstance(statement, ast.Try | ast.TryStar):
            return self.build_try(statement)
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign,
                                  ast.Expr, ast.Delete)):
            return self.build_call_statement(statement)
        self.notes_list.append(Note(statement.lineno, (
            f"{type(statement).__name__} statement is not drawn "
            "(not supported in this version)")))
        return []

    def note_else_none(self, statement: ast.For | ast.AsyncFor | ast.While,
                       keyword_str: str) -> None:
        """Note a loop's else clause, which is not drawn.

        Args:
            statement: The loop.
            keyword_str: "for" or "while".

        Returns:
            None.
        """
        if statement.orelse:
            self.notes_list.append(Note(statement.orelse[0].lineno, (
                f"the else clause of the {keyword_str} loop at line "
                f"{statement.lineno} is not drawn")))

    def build_with(self, statement: ast.With | ast.AsyncWith) -> list[Item]:
        """Build a with block, remembering open() file handles.

        Args:
            statement: The with statement.

        Returns:
            The body's items, plus an open step for handles the body
            does not visibly read or write.
        """
        opened_list = []
        for item in statement.items:
            call = item.context_expr
            if (isinstance(call, ast.Call)
                    and dtypes.read_called_name_str(call.func) == "open"
                    and isinstance(item.optional_vars, ast.Name)
                    and call.args):
                handle_str = item.optional_vars.id
                self.handles_dict[handle_str] = (
                    self.label_str(call.args[0]), check_open_writes_bool(call))
                opened_list.append(handle_str)
        items_list = self.build_items(statement.body)
        for handle_str in opened_list:
            label_str, is_output = self.handles_dict.pop(handle_str)
            if handle_str not in self.used_handles_set:
                verb_str = "write" if is_output else "read"
                items_list.insert(0, Step(
                    PROCESS_KIND, "", describe.make_sentence_str(
                        f"open {label_str} to {verb_str}"),
                    line=statement.lineno,
                    sources=[Source(DATA_KIND, label_str, is_output)]))
            self.used_handles_set.discard(handle_str)
        return items_list

    def build_try(self, statement: ast.Try | ast.TryStar) -> list[Item]:
        """Build a try statement: its body, else and finally parts.

        Args:
            statement: The try statement.

        Returns:
            The items of the main path; handlers are reported as notes.
        """
        for handler in statement.handlers:
            caught_str = (ast.unparse(handler.type) if handler.type
                          else "any exception")
            self.notes_list.append(Note(handler.lineno, (
                f"the handler for {caught_str} of the try at line "
                f"{statement.lineno} is not drawn")))
        return (self.build_items(statement.body)
                + self.build_items(statement.orelse)
                + self.build_items(statement.finalbody))

    def build_call_statement(self, statement: ast.stmt) -> list[Item]:
        """Build the steps of a statement with a local call or I/O.

        Args:
            statement: An assignment or expression statement.

        Returns:
            One step, or one per function of a .pipe() chain.
        """
        value = getattr(statement, "value", None)
        targets_list = list_assignment_targets_list(statement)
        if isinstance(value, ast.Call) and list_pipe_chain_list(value):
            return self.build_pipe_steps(value, targets_list)
        call = self.find_main_call(statement)
        sources_list = [source for source in (
            self.find_io_source(node) for node in ast.walk(statement)
            if isinstance(node, ast.Call)) if source]
        function_info = self.resolve_function(call) if call else None
        if function_info is not None:
            step = self.build_function_step(call, function_info, targets_list)
        else:
            step = self.build_library_step(call, targets_list)
        step.sources = sources_list
        step.line = statement.lineno
        return [step]

    def find_main_call(self, statement: ast.stmt) -> ast.Call | None:
        """The call a statement is drawn as: local first, then I/O.

        Args:
            statement: The statement.

        Returns:
            The first call to a script or developed function, else the
            first call doing I/O, else None.
        """
        calls_list = [node for node in ast.walk(statement)
                      if isinstance(node, ast.Call)]
        for call in calls_list:
            if self.resolve_function(call):
                return call
        for call in calls_list:
            if self.check_io_bool(call):
                return call
        return None

    def build_function_step(self, call: ast.Call, function_info: FunctionInfo,
                            targets_list: list[ast.expr]) -> Step:
        """A titled step for a call to a script or developed function.

        Args:
            call: The call.
            function_info: What the source says about the function.
            targets_list: Assignment targets of the statement.

        Returns:
            The step, coloured by its developed module.
        """
        annotations_dict = dict(function_info.parameters)
        positional_list = [name_str for name_str, _ in
                           function_info.parameters]
        if positional_list and positional_list[0] in ("self", "cls"):
            positional_list = positional_list[1:]
        inputs_list = []
        for index_int, argument in enumerate(call.args):
            name_str = (positional_list[index_int]
                        if index_int < len(positional_list) else "")
            inputs_list.append(self.make_port(
                argument, annotations_dict.get(name_str, "")))
        for keyword in call.keywords:
            inputs_list.append(self.make_port(
                keyword.value, annotations_dict.get(keyword.arg or "", "")))
        module_str = function_info.module
        if module_str and module_str not in self.modules_list:
            self.modules_list.append(module_str)
        name_str = dtypes.read_called_name_str(call.func).split(".")[-1]
        description_str = (describe.make_sentence_str(function_info.summary)
                           or describe.describe_name_str(name_str))
        return Step(PROCESS_KIND, name_str, description_str, inputs_list,
                    self.output_ports_list(targets_list,
                                           function_info.returns),
                    module_str)

    def build_library_step(self, call: ast.Call | None,
                           targets_list: list[ast.expr]) -> Step:
        """An untitled step for an I/O call of a library.

        Args:
            call: The I/O call, or None.
            targets_list: Assignment targets of the statement.

        Returns:
            The step.
        """
        if call is None:
            return Step(PROCESS_KIND, "", "Run the statement.")
        name_str = dtypes.read_called_name_str(call.func)
        inputs_list = [self.make_port(argument) for argument in call.args
                       if isinstance(argument, (ast.Name, ast.Attribute))
                       and ast.unparse(argument) not in self.handles_dict]
        receiver = call.func.value if isinstance(call.func,
                                                 ast.Attribute) else None
        if (isinstance(receiver, ast.Name)
                and receiver.id not in self.info.imported
                and receiver.id not in self.handles_dict):
            inputs_list.insert(0, self.make_port(receiver))
        result_dtype_str = dtypes.infer_value_dtype_str(call)
        return Step(PROCESS_KIND, "", describe.describe_name_str(name_str),
                    inputs_list,
                    self.output_ports_list(targets_list, result_dtype_str))

    def build_pipe_steps(self, value: ast.Call,
                         targets_list: list[ast.expr]) -> list[Item]:
        """One step per function of a ``data.pipe(f).pipe(g)`` chain.

        Args:
            value: The outermost pipe call.
            targets_list: Assignment targets of the statement.

        Returns:
            The steps in the order the functions run.
        """
        chain_list = list_pipe_chain_list(value)
        base = chain_list[0].func.value
        current_port = self.make_port(base)
        steps_list: list[Item] = []
        for index_int, pipe_call in enumerate(chain_list):
            function_expr = pipe_call.args[0]
            fake_call = ast.Call(function_expr, [base, *pipe_call.args[1:]],
                                 pipe_call.keywords)
            function_info = self.resolve_function(fake_call) or FunctionInfo(
                dtypes.read_called_name_str(function_expr) or "function")
            is_last = index_int == len(chain_list) - 1
            step = self.build_function_step(fake_call, function_info,
                                            targets_list if is_last else [])
            step.inputs[0] = current_port
            if not is_last:
                step.outputs = [Port(
                    current_port.name, dtypes.pick_known_dtype_str(
                        function_info.returns, current_port.dtype))]
                current_port = step.outputs[0]
            step.line = pipe_call.lineno
            steps_list.append(step)
        return steps_list


def split_jump_tuple(body_list: list[ast.stmt]
                     ) -> tuple[list[ast.stmt], str]:
    """Separate a trailing continue, break or return from a body.

    Args:
        body_list: The statements of an if or else path.

    Returns:
        The statements before the jump and the jump keyword, or the
        body unchanged and "".
    """
    jumps_dict = {ast.Continue: "continue", ast.Break: "break",
                  ast.Return: "return"}
    if body_list and type(body_list[-1]) in jumps_dict:
        return body_list[:-1], jumps_dict[type(body_list[-1])]
    return body_list, ""


def extract_file_name_str(path_str: str) -> str:
    """The last component of a path or URL, or the text itself.

    Args:
        path_str: A path, URL or name.

    Returns:
        The file name, such as "trips.csv".
    """
    name_str = PurePath(path_str.replace("\\", "/")).name
    return name_str or path_str


def check_string_argument_bool(call: ast.Call) -> bool:
    """Whether a call's first argument is a string literal.

    Args:
        call: The call.

    Returns:
        True for calls like config.read("settings.ini").
    """
    return bool(call.args) and isinstance(call.args[0], ast.Constant) and (
        isinstance(call.args[0].value, str))


def check_open_writes_bool(call: ast.Call) -> bool:
    """Whether an open() call opens its file for writing.

    Args:
        call: The open call.

    Returns:
        True for modes containing "w", "a", "x" or "+".
    """
    mode = call.args[1] if len(call.args) > 1 else next(
        (keyword.value for keyword in call.keywords
         if keyword.arg == "mode"), None)
    return (isinstance(mode, ast.Constant) and isinstance(mode.value, str)
            and any(letter in mode.value for letter in "wax+"))


def list_assignment_targets_list(statement: ast.stmt) -> list[ast.expr]:
    """The assignment targets of a statement.

    Args:
        statement: Any statement.

    Returns:
        The targets of an assignment, else an empty list.
    """
    if isinstance(statement, ast.Assign):
        return list(statement.targets)
    if isinstance(statement, (ast.AnnAssign, ast.AugAssign)):
        return [statement.target]
    return []


def list_pipe_chain_list(value: ast.Call) -> list[ast.Call]:
    """The ``.pipe(function, ...)`` calls of a chain, innermost first.

    Args:
        value: The outermost call.

    Returns:
        The pipe calls, or an empty list when value is not a chain.
    """
    chain_list = []
    current = value
    while (isinstance(current, ast.Call)
           and isinstance(current.func, ast.Attribute)
           and current.func.attr == "pipe" and current.args):
        chain_list.append(current)
        current = current.func.value
    return list(reversed(chain_list))


def build_flow(info: ScriptInfo) -> Flow:
    """Build the flow of a parsed script.

    Args:
        info: The parsed script and its developed modules.

    Returns:
        The Flow from the entry point, with notes for what is left out.
    """
    builder = FlowBuilder(info)
    items_list = builder.build_entry_items(
        find_entry_statements_list(info.tree))
    return Flow(info.path.name, items_list, builder.modules_list,
                builder.notes_list)
