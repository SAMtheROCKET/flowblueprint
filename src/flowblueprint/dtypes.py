"""Data types from evidence in the source, never from running it.

Evidence, strongest first: annotations of the called function, the
known result type of common library calls, literal values, the type
already recorded for a variable, and conventional name suffixes such as
"_df" or "_list". Anything else stays "unknown".
"""

import ast

from flowblueprint.model import UNKNOWN_DTYPE_STR

# Conventional name suffixes and the types they state.
SUFFIX_DTYPES_TUPLE = (
    ("_df", "DataFrame"), ("_series", "Series"), ("_list", "list"),
    ("_dict", "dict"), ("_tuple", "tuple"), ("_set", "set"),
    ("_str", "str"), ("_int", "int"), ("_float", "float"),
    ("_bool", "bool"), ("_arr", "ndarray"), ("_array", "ndarray"),
    ("_path", "Path"), ("_gdf", "GeoDataFrame"),
)

# Result types of common library calls, by the called name's last part.
CALL_DTYPES_DICT = {
    "read_csv": "DataFrame", "read_parquet": "DataFrame",
    "read_excel": "DataFrame", "read_json": "DataFrame",
    "read_feather": "DataFrame", "read_pickle": "DataFrame",
    "read_table": "DataFrame", "read_sql": "DataFrame",
    "read_sql_query": "DataFrame", "read_sql_table": "DataFrame",
    "read_hdf": "DataFrame", "DataFrame": "DataFrame",
    "concat": "DataFrame", "merge": "DataFrame",
    "pivot_table": "DataFrame", "read_file": "GeoDataFrame",
    "Series": "Series", "array": "ndarray", "zeros": "ndarray",
    "ones": "ndarray", "arange": "ndarray", "linspace": "ndarray",
    "loadtxt": "ndarray", "genfromtxt": "ndarray",
    "Path": "Path", "ConfigParser": "ConfigParser",
    "open": "file", "read_text": "str", "read_bytes": "bytes",
    "len": "int", "int": "int", "float": "float", "str": "str",
    "bool": "bool", "list": "list", "dict": "dict", "set": "set",
    "tuple": "tuple", "sorted": "list", "range": "range",
    "enumerate": "enumerate", "zip": "zip", "round": "int | float",
    "datetime": "datetime", "now": "datetime",
    "to_datetime": "datetime | Series", "Figure": "Figure",
    "figure": "Figure", "subplots": "tuple[Figure, Axes]",
}

LITERAL_DTYPES_DICT = {
    ast.List: "list", ast.ListComp: "list", ast.Dict: "dict",
    ast.DictComp: "dict", ast.Set: "set", ast.SetComp: "set",
    ast.Tuple: "tuple", ast.JoinedStr: "str",
    ast.GeneratorExp: "generator",
}


def infer_name_dtype_str(name_str: str) -> str:
    """The type a variable name states by its suffix.

    Args:
        name_str: A variable name such as "vehicle_df".

    Returns:
        The type, such as "DataFrame", or "unknown".
    """
    lowered_str = name_str.lower()
    if lowered_str == "df":
        return "DataFrame"
    for suffix_str, dtype_str in SUFFIX_DTYPES_TUPLE:
        if lowered_str.endswith(suffix_str):
            return dtype_str
    return UNKNOWN_DTYPE_STR


def infer_value_dtype_str(value: ast.expr) -> str:
    """The type of a literal or a well-known call, from its syntax.

    Args:
        value: The assigned expression.

    Returns:
        The type, or "unknown".
    """
    if isinstance(value, ast.Constant):
        if value.value is None:
            return "None"
        return type(value.value).__name__
    for node_type, dtype_str in LITERAL_DTYPES_DICT.items():
        if isinstance(value, node_type):
            return dtype_str
    if isinstance(value, ast.Call):
        return CALL_DTYPES_DICT.get(read_called_name_str(value.func).split(
            ".")[-1], UNKNOWN_DTYPE_STR)
    if isinstance(value, ast.Compare | ast.BoolOp):
        return "bool"
    return UNKNOWN_DTYPE_STR


def read_called_name_str(func: ast.expr) -> str:
    """The dotted name of a called function, such as "pd.read_csv".

    Args:
        func: The call's func expression.

    Returns:
        The dotted name; for calls on other expressions (such as a
        method on a call result) the parts after the expression, such
        as ".pipe"; "" when there is no name at all.
    """
    parts_list = []
    while isinstance(func, ast.Attribute):
        parts_list.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts_list.append(func.id)
    elif parts_list:
        parts_list.append("")
    return ".".join(reversed(parts_list))


def split_tuple_annotation_list(annotation_str: str,
                                count_int: int) -> list[str]:
    """Split "tuple[A, B]" into ["A", "B"] when it has count_int parts.

    Args:
        annotation_str: A return annotation as written.
        count_int: The number of unpacking targets.

    Returns:
        One type per target, or "unknown" for each when the annotation
        is not a tuple of that length.
    """
    try:
        node = ast.parse(annotation_str, mode="eval").body
    except SyntaxError:
        return [UNKNOWN_DTYPE_STR] * count_int
    if (isinstance(node, ast.Subscript)
            and read_called_name_str(node.value).split(".")[-1]
            in ("tuple", "Tuple")
            and isinstance(node.slice, ast.Tuple)
            and len(node.slice.elts) == count_int):
        return [ast.unparse(element) for element in node.slice.elts]
    return [UNKNOWN_DTYPE_STR] * count_int


def pick_known_dtype_str(*candidates_tuple: str) -> str:
    """The first candidate type that is known.

    Args:
        *candidates_tuple: Types in order of strength.

    Returns:
        The first one other than "" and "unknown", else "unknown".
    """
    for candidate_str in candidates_tuple:
        if candidate_str and candidate_str != UNKNOWN_DTYPE_STR:
            return candidate_str
    return UNKNOWN_DTYPE_STR
