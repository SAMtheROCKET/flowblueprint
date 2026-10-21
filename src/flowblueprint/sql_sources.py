"""Recognize SQL file reads from literal query-loader arguments."""

import ast

from flowblueprint.dtypes import read_called_name_str
from flowblueprint.model import DATA_KIND, DATABASE_KIND, Source

SQL_EXECUTE_SET = frozenset(("execute", "executemany", "executescript"))

SQL_LOADERS_SET = frozenset((
    "get_sql_query", "load_sql", "load_sql_str", "load_query",
    "read_sql_file"))


def find_sql_source(call_node: ast.Call) -> Source | None:
    """Describe a visible SQL asset read without resolving or opening it.

    Args:
        call_node (ast.Call): Source call expression.
    Returns:
        Source | None: A query file shape when a literal path is visible.
    Warnings:
        Loader names are syntax evidence; file existence and database
        behavior are not inferred. Dynamic paths remain unresolved.
    """
    name_str = read_called_name_str(call_node.func).rsplit(".", 1)[-1]
    generated_bool = name_str.startswith("_funcloom_load_sql_str")
    if name_str in SQL_LOADERS_SET or generated_bool:
        values_list = [*call_node.args,
                       *(item.value for item in call_node.keywords)]
    elif name_str in ("read_text", "read_bytes") and isinstance(
            call_node.func, ast.Attribute):
        values_list = list(ast.walk(call_node.func.value))
    else:
        return None
    paths_list = [node.value for node in values_list
                  if isinstance(node, ast.Constant)
                  and isinstance(node.value, str)
                  and node.value.lower().endswith(".sql")]
    if len(paths_list) != 1:
        return None
    label_str = paths_list[0]
    if generated_bool and "/" not in label_str and "\\" not in label_str:
        label_str = "sql/" + label_str
    return Source(DATA_KIND, label_str)


def find_sql_connection_source(call_node: ast.Call) -> Source | None:
    """Show the visible connection used by common SQL execution methods.

    Args:
        call_node (ast.Call): Python call syntax.
    Returns:
        Source | None: Connection input to an execute-like operation.
    Warnings:
        The receiver is syntax evidence, not a resolved database or table.
        A connection input does not assert that the query is read-only.
    """
    if isinstance(call_node.func, ast.Attribute) and (
            call_node.func.attr in SQL_EXECUTE_SET):
        receiver_str = ast.unparse(call_node.func.value)
        return Source(DATABASE_KIND, receiver_str + " (SQL connection)")
    return None
