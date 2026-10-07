"""Short, deterministic descriptions of steps.

A function's docstring summary wins. Without one, the description is
built from the code itself: the function name read as a verb phrase,
a known library operation, or the plain statement's effect. No text is
invented beyond what the names and syntax say; an override file can
replace any description.
"""

import ast
import re

from flowblueprint.dtypes import read_called_name_str

# Common leading verbs of function names, for the verb-first check.
VERBS_FROZENSET = frozenset("""
add aggregate align analyse analyze append apply assign attach average
build bucket cache calculate call cast check classify clean clear clip
close cluster collect combine compare compile compute concat configure
connect convert copy count create crop cut decode deduplicate define
delete derive describe detect diff discard display download draw drop
dump encode enrich ensure estimate evaluate expand explode export
extend extract fetch fill filter find fit flag flatten format generate
get group handle index infer init initialise initialize insert
interpolate join keep label list load locate log make map mark mask
measure merge migrate normalise normalize open order parse partition
pick pivot plot predict prepare preprocess print process prune publish
push query rank read rebuild record reduce refresh register reindex
remove rename render reorder repair replace report resample reset
reshape resolve restore round run sample save scale scan score select
send set setup shift show shuffle simulate slice smooth sort split
stack standardise standardize start stop store summarise summarize
sync tabulate tag test tokenize train transform translate trim tune
unpack update upload validate verify visualise visualize wrap write
""".split())

# Library operations with a fixed meaning, by the called name's last part.
LIBRARY_PHRASES_DICT = {
    "read_csv": "Read the CSV table", "read_parquet": "Read the Parquet table",
    "read_excel": "Read the Excel sheet", "read_json": "Read the JSON table",
    "read_sql": "Query the database", "read_sql_query": "Query the database",
    "read_sql_table": "Read the database table",
    "read_pickle": "Load the pickled data", "read_feather": "Read the table",
    "read_file": "Read the geodata file", "read": "Read the settings",
    "load": "Load the saved data", "loads": "Parse the text",
    "loadtxt": "Load the numeric text file", "open": "Open the file",
    "to_csv": "Save as CSV", "to_parquet": "Save as Parquet",
    "to_excel": "Save as Excel", "to_json": "Save as JSON",
    "to_pickle": "Save as pickle", "to_sql": "Write to the database",
    "dump": "Save the data", "save": "Save the array",
    "savefig": "Save the figure", "concat": "Concatenate the tables",
    "merge": "Merge the tables", "groupby": "Group the rows",
    "drop_duplicates": "Remove duplicate rows", "dropna": "Drop empty values",
    "fillna": "Fill missing values", "sort_values": "Sort the rows",
    "apply": "Apply the function to each row", "connect": "Connect",
    "ConfigParser": "Create the settings reader",
}

CAMEL_BOUNDARY_PATTERN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# Statements whose code is at most this long are shown as written.
SHORT_CODE_INT = 46
LOG_METHODS_FROZENSET = frozenset((
    "debug", "info", "warning", "warn", "error", "exception", "critical"))
# Facts about a function body, by the called name's last part (or the
# whole dotted name), for functions without a docstring.
CALL_FACTS_DICT = {
    "open": "opens {0}", "DictReader": "reads CSV rows",
    "reader": "reads CSV rows", "writer": "writes CSV rows",
    "DictWriter": "writes CSV rows", "read_csv": "reads the CSV table",
    "to_csv": "saves a CSV file", "load": "loads saved data",
    "dump": "saves data", "loads": "parses text", "dumps": "formats text",
    "connect": "connects to the database", "execute": "runs SQL",
    "executemany": "runs SQL", "commit": "commits to the database",
    "get": "", "post": "", "savefig": "saves the figure",
    "makedirs": "creates folder {0}", "mkdir": "creates a folder",
    "listdir": "lists the files of {0}", "glob": "finds files",
    "raise_for_status": "checks the HTTP status",
}
WEB_MODULES_TUPLE = ("requests", "httpx", "urllib", "aiohttp")


def split_words_list(name_str: str) -> list[str]:
    """Split snake_case and camelCase names into lowercase words.

    Args:
        name_str: A function or variable name.

    Returns:
        Its words, such as ["load", "vehicle", "data"].
    """
    spaced_str = CAMEL_BOUNDARY_PATTERN.sub("_", name_str)
    return [word.lower() for word in re.split(r"[_\W]+", spaced_str)
            if word]


def check_verb_first_bool(name_str: str) -> bool:
    """Whether a name begins with a common verb.

    Args:
        name_str: A function name.

    Returns:
        True for names like "calculate_duration".
    """
    parts_list = split_words_list(name_str)
    return bool(parts_list) and parts_list[0] in VERBS_FROZENSET


def make_sentence_str(text_str: str) -> str:
    """Capitalise the first letter and end with a full stop.

    Args:
        text_str: A phrase.

    Returns:
        The phrase as a sentence.
    """
    text_str = text_str.strip()
    if not text_str:
        return ""
    text_str = text_str[0].upper() + text_str[1:]
    return text_str if text_str[-1] in ".!?" else text_str + "."


def describe_name_str(name_str: str) -> str:
    """A description read from a function name alone.

    Args:
        name_str: A function name, possibly dotted.

    Returns:
        "Calculate duration." for "calculate_duration"; "Run x." when
        the name does not start with a verb.
    """
    short_str = name_str.split(".")[-1]
    phrase_str = LIBRARY_PHRASES_DICT.get(short_str)
    if phrase_str:
        return make_sentence_str(phrase_str)
    parts_list = split_words_list(short_str)
    if parts_list and parts_list[0] in VERBS_FROZENSET:
        return make_sentence_str(" ".join(parts_list))
    return make_sentence_str(f"run {short_str}")


def join_names_str(names_list: list[str]) -> str:
    """Join names as "a", "a and b" or "a, b and c".

    Args:
        names_list: Names in order.

    Returns:
        The joined text.
    """
    if len(names_list) <= 1:
        return "".join(names_list)
    return ", ".join(names_list[:-1]) + " and " + names_list[-1]


def list_target_names_list(targets_list: list[ast.expr]) -> list[str]:
    """The names assigned by assignment targets, as written.

    Args:
        targets_list: Assignment targets.

    Returns:
        One name per plain or unpacked target, in order.
    """
    names_list = []
    for target in targets_list:
        if isinstance(target, (ast.Tuple, ast.List)):
            names_list.extend(list_target_names_list(list(target.elts)))
        elif isinstance(target, ast.Starred):
            names_list.extend(list_target_names_list([target.value]))
        else:
            names_list.append(ast.unparse(target))
    return names_list


def describe_call_statement_str(call: ast.Call, targets_list: list[str]
                                ) -> str:
    """Describe a plain statement whose value is a library call.

    Args:
        call: The call.
        targets_list: Names it assigns to (may be empty).

    Returns:
        A phrase such as "append row to rows_list".
    """
    name_str = read_called_name_str(call.func)
    short_str = name_str.split(".")[-1]
    receiver_str = name_str.rsplit(".", 1)[0] if "." in name_str else ""
    first_str = ast.unparse(call.args[0]) if call.args else ""
    if short_str in ("append", "add") and receiver_str and first_str:
        return f"{short_str} {first_str} to {receiver_str}"
    if short_str == "extend" and receiver_str and first_str:
        return f"extend {receiver_str} with {first_str}"
    if short_str == "print" or (short_str in LOG_METHODS_FROZENSET
                                and "log" in receiver_str.lower()):
        verb_str = "print" if short_str == "print" else f"log {short_str}"
        arguments_str = ", ".join(ast.unparse(argument)
                                  for argument in call.args)
        return shorten_code_str(f"{verb_str} {arguments_str}".strip())
    if short_str in ("makedirs", "mkdir") and first_str:
        return f"create folder {first_str}"
    code_str = ast.unparse(call)
    if targets_list and len(code_str) <= SHORT_CODE_INT:
        return f"set {join_names_str(targets_list)} = {code_str}"
    if targets_list:
        return f"compute {join_names_str(targets_list)} with {short_str}"
    phrase_str = LIBRARY_PHRASES_DICT.get(short_str)
    return phrase_str.lower() if phrase_str else f"call {name_str}"


def describe_statement_str(statement: ast.stmt) -> str:
    """Describe one plain statement as a short phrase.

    Args:
        statement: A statement without calls to local functions.

    Returns:
        A phrase such as "set total_int" or "update count_int".
    """
    if isinstance(statement, ast.AugAssign):
        return f"update {ast.unparse(statement.target)}"
    if isinstance(statement, (ast.Assign, ast.AnnAssign)):
        targets_list = (statement.targets if isinstance(statement, ast.Assign)
                        else [statement.target])
        names_list = list_target_names_list(targets_list)
        if isinstance(statement.value, ast.Call):
            return describe_call_statement_str(statement.value, names_list)
        value_str = (ast.unparse(statement.value)
                     if statement.value is not None else "")
        if value_str and len(value_str) <= SHORT_CODE_INT:
            return f"set {join_names_str(names_list)} = {value_str}"
        return f"set {join_names_str(names_list)}"
    if isinstance(statement, ast.Expr) and isinstance(statement.value,
                                                      ast.Call):
        return describe_call_statement_str(statement.value, [])
    if isinstance(statement, ast.Delete):
        names_list = [ast.unparse(target) for target in statement.targets]
        return f"delete {join_names_str(names_list)}"
    return f"run line {statement.lineno}"


def shorten_code_str(text_str: str) -> str:
    """Cut code shown in a block to a readable length.

    Args:
        text_str: A phrase that ends in code.

    Returns:
        The text, cut with "..." past 60 characters.
    """
    return text_str if len(text_str) <= 60 else text_str[:57] + "..."


def describe_own_function_str(name_str: str,
                              body_list: list[ast.stmt]) -> str:
    """Describe a script function without a docstring from its body.

    Args:
        name_str: The function name.
        body_list: Its statements.

    Returns:
        The name read as a verb phrase, then up to three facts the
        body shows (files, loops, web and database calls) and what it
        returns, such as "Load sales: opens path; reads CSV rows;
        returns rows."
    """
    words_list = split_words_list(name_str)
    phrase_str = (" ".join(words_list) if check_verb_first_bool(name_str)
                  else f"run {name_str}")
    facts_list = list_body_facts_list(body_list)[:3]
    if body_list and isinstance(body_list[-1], ast.Return) and (
            body_list[-1].value is not None):
        facts_list.append(shorten_code_str(
            "returns " + ast.unparse(body_list[-1].value)))
    if not facts_list:
        return make_sentence_str(phrase_str)
    return make_sentence_str(f"{phrase_str}: {'; '.join(facts_list)}")


def list_body_facts_list(body_list: list[ast.stmt]) -> list[str]:
    """Facts a function body shows, in source order, without repeats.

    Args:
        body_list: The statements.

    Returns:
        Phrases such as "loops over rows" or "calls the web API".
    """
    facts_list: list[str] = []
    nodes_list = sorted(
        (node for statement in body_list for node in ast.walk(statement)
         if hasattr(node, "lineno")),
        key=lambda node: (node.lineno, node.col_offset))
    for node in nodes_list:
        fact_str = ""
        if isinstance(node, (ast.For, ast.AsyncFor)):
            fact_str = f"loops over {ast.unparse(node.iter)}"
        elif isinstance(node, ast.While):
            fact_str = f"repeats while {ast.unparse(node.test)}"
        elif isinstance(node, ast.Call):
            fact_str = describe_call_fact_str(node)
        fact_str = shorten_code_str(fact_str) if fact_str else ""
        if fact_str and fact_str not in facts_list:
            facts_list.append(fact_str)
    return facts_list


def describe_call_fact_str(call: ast.Call) -> str:
    """A body fact for one call, or "".

    Args:
        call: The call.

    Returns:
        "calls the web API" for requests-style calls, the
        CALL_FACTS_DICT phrase for known operations, else "".
    """
    name_str = read_called_name_str(call.func)
    if name_str.split(".")[0] in WEB_MODULES_TUPLE:
        return "calls the web API"
    template_str = CALL_FACTS_DICT.get(name_str.split(".")[-1], "")
    first_str = ast.unparse(call.args[0]) if call.args else "it"
    return template_str.format(first_str)


def describe_group_str(statements_list: list[ast.stmt],
                       limit_int: int = 3) -> str:
    """Describe consecutive plain statements as one sentence.

    Args:
        statements_list: The statements, in order.
        limit_int: How many statements to name before summarising.

    Returns:
        A sentence such as "Set limit_int; update total_float."
    """
    phrases_list = []
    for statement in statements_list:
        phrase_str = describe_statement_str(statement)
        if phrase_str not in phrases_list:
            phrases_list.append(phrase_str)
    shown_list = phrases_list[:limit_int]
    text_str = "; ".join(shown_list)
    hidden_int = len(phrases_list) - len(shown_list)
    if hidden_int:
        text_str += f"; and {hidden_int} more"
    return make_sentence_str(text_str)
