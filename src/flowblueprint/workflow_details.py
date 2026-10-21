"""Supplement operational canvases with explicitly declared function pages."""

import ast
from pathlib import Path

from flowblueprint.drawio import render_drawio_pages_str
from flowblueprint.flow import FlowBuilder
from flowblueprint.reference_layout import layout_reference_canvas
from flowblueprint.source import describe_function, load_script

MAX_FUNCTION_PAGES_INT = 100
FUNCTION_NODES_TUPLE = (ast.FunctionDef, ast.AsyncFunctionDef)


def collect_function_definitions_list(
    tree_node: ast.AST, prefix_str: str = "",
) -> list[tuple[str, ast.AST]]:
    """List lexical function definitions with unambiguous qualified names.

    Args:
        tree_node: Module, class, or function body.
        prefix_str: Lexical owner name.
    Returns:
        list: Qualified names paired with source definitions.
    Warnings:
        Presence is not evidence that a function is called at runtime.
    """
    results_list = []
    for child_node in ast.iter_child_nodes(tree_node):
        if isinstance(child_node, (*FUNCTION_NODES_TUPLE, ast.ClassDef)):
            name_str = prefix_str + child_node.name
            if isinstance(child_node, FUNCTION_NODES_TUPLE):
                results_list.append((name_str, child_node))
            results_list.extend(collect_function_definitions_list(
                child_node, name_str + "."))
        else:
            results_list.extend(collect_function_definitions_list(
                child_node, prefix_str))
    return results_list


def add_file_detail_pages_none(
    staging_path: Path, path_str: str, pages_list: list,
    notes_list: list[str], max_blocks_int: int,
) -> None:
    """Draw each function of one checked file on a page of its own.

    Args:
        staging_path: Bundle containing the final project copy.
        path_str: The file, relative to the project copy.
        pages_list: Pages so far (extended, up to the page limit).
        notes_list: Limitations so far (extended).
        max_blocks_int: Target blocks per diagram column.
    Returns:
        None: Extends pages_list and notes_list.
    Warnings:
        Stops when MAX_FUNCTION_PAGES_INT pages exist.
    """
    source_info = load_script(staging_path / "project" / path_str)
    for name_str, function_node in collect_function_definitions_list(
            source_info.tree):
        if len(pages_list) == MAX_FUNCTION_PAGES_INT:
            return
        function_info = describe_function(function_node, "")
        function_info.name = name_str
        flow_info = FlowBuilder(source_info).build_function_flow(
            function_info, path_str)
        notes_list.extend(f"{path_str}:{note_info.line}: {note_info.message}"
                          for note_info in flow_info.notes)
        title_str = (f"Declared body: {path_str}:{function_node.lineno}: "
                     f"{name_str}")
        pages_list.append(layout_reference_canvas(
            [flow_info], title_str, max_blocks_int))


def write_function_details_list(
    staging_path: Path, files_list: list[dict], max_blocks_int: int,
) -> list[str]:
    """Draw function bodies separately from the observed entry flow.

    Args:
        staging_path: Bundle containing the final project copy.
        files_list: RefacTrail's checked Python paths.
        max_blocks_int: Target blocks per diagram column.
    Returns:
        list[str]: Explicit limitations including any page cap.
    Warnings:
        Closures, decorators, dynamic dispatch and execution are unverified.
    """
    pages_list = []
    notes_list = ["Function pages show declared bodies, not runtime calls; "
                  "closure values and dynamic dispatch remain unresolved."]
    for file_dict in files_list:
        if file_dict["status"] != "checked":
            continue
        add_file_detail_pages_none(staging_path, file_dict["path"],
                                   pages_list, notes_list, max_blocks_int)
        if len(pages_list) == MAX_FUNCTION_PAGES_INT:
            notes_list.append("Function detail limit of 100 pages reached; "
                              "additional definitions may be omitted.")
            break
    if pages_list:
        (staging_path / "function_details.drawio").write_text(
            render_drawio_pages_str(pages_list), "utf-8")
    else:
        notes_list.append("No function bodies were available to draw.")
    return notes_list
