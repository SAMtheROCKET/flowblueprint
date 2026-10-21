"""Read operational entry flows for the supplied architecture style."""

import ast
from pathlib import Path

from flowblueprint.flow import (
    FlowBuilder, build_flow, find_entry_statements_list,
)
from flowblueprint.model import Flow, Note
from flowblueprint.project import ENTRY_KIND, NOTEBOOK_KIND, load_project
from flowblueprint.source import load_script

MAX_REFERENCE_ENTRIES_INT = 60


def read_reference_flow(source_path: Path) -> Flow:
    """Show a delegated local entry body beneath its original call.

    Args:
        source_path: Script or notebook to parse.
    Returns:
        Flow: Entry operations, including a bounded local handover.
    Warnings:
        A declared method body is static evidence, not dispatch proof.
        Only a sole argument-free expression call is expanded.
    """
    source_info = load_script(source_path)
    compile(source_info.tree, str(source_path), "exec")
    flow_info = build_flow(source_info)
    statements_list = find_entry_statements_list(source_info.tree)
    if len(statements_list) != 1:
        return flow_info
    statement_info = statements_list[0]
    call_info = (statement_info.value
                 if isinstance(statement_info, ast.Expr) else None)
    if not isinstance(call_info, ast.Call) or (
            call_info.args or call_info.keywords):
        return flow_info
    function_info = FlowBuilder(source_info).resolve_function(call_info)
    if not function_info or not function_info.body:
        return flow_info
    if function_info.source_path is None:
        return flow_info  # Existing same-module entry handling applies.
    builder_info = FlowBuilder(load_script(function_info.source_path))
    detail_info = builder_info.build_function_flow(
        function_info, function_info.source_path.name)
    flow_info.items.extend(detail_info.items)
    flow_info.modules = sorted(set(flow_info.modules + detail_info.modules))
    flow_info.notes.extend(detail_info.notes)
    flow_info.notes.append(Note(statement_info.lineno, (
        f"Showing declared body of {function_info.source_path.name}:"
        f"{function_info.owner_class}.{function_info.name}; "
        "runtime dispatch and constructor effects are unverified.")))
    return flow_info


def select_entry_paths_list(
    source_path: Path, entries_list: list[str] | None = None,
    include_tests_bool: bool = False,
) -> tuple[list[Path], list[str]]:
    """Select entry scripts without silently choosing an arbitrary module.

    Args:
        source_path: Script, notebook, or repository.
        entries_list: Explicit relative entry paths for a repository.
        include_tests_bool: Include test entry points when discovering.
    Returns:
        tuple: Paths and discovery limitations.
    Warnings:
        Missing, escaping, linked, or excessive selections are refused.
    """
    source_path = source_path.resolve()
    if not source_path.is_dir():
        if entries_list:
            raise ValueError("--entry requires a project folder")
        return [source_path], []
    project_info = load_project(source_path, include_tests_bool)
    selected_list = entries_list if entries_list is not None else [
        info.path.as_posix() for info in project_info.files
        if info.kind in (ENTRY_KIND, NOTEBOOK_KIND)]
    if not selected_list:
        raise ValueError("No entry scripts detected; select --entry PATH")
    if len(selected_list) > MAX_REFERENCE_ENTRIES_INT:
        raise ValueError("Select at most 60 entry scripts with --entry")
    paths_list = []
    for relative_str in dict.fromkeys(selected_list):
        path_info = source_path / relative_str
        resolved_path = path_info.resolve()
        if (Path(relative_str).is_absolute()
                or not resolved_path.is_relative_to(source_path)):
            raise ValueError(f"Entry escapes input project: {relative_str}")
        if not path_info.is_file() or path_info.suffix not in (
                ".py", ".ipynb") or path_info.is_symlink():
            raise ValueError(f"Entry is not a Python file: {relative_str}")
        paths_list.append(resolved_path)
    return paths_list, list(project_info.notes)


def read_reference_flows_tuple(
    source_path: Path, entries_list: list[str] | None = None,
    include_tests_bool: bool = False, overrides_path: Path | None = None,
) -> tuple[list[Flow], list[str]]:
    """Load selected flows and retain file-qualified uncertainty notes.

    Args:
        source_path: Script, notebook, or repository.
        entries_list: Relative paths, or None to detect entries.
        include_tests_bool: Include test scripts during discovery.
        overrides_path: Optional domain titles and descriptions.
    Returns:
        tuple: Operational flows and explicit analysis notes.
    Warnings:
        Parsing failures are errors; target code is never executed.
    """
    paths_list, notes_list = select_entry_paths_list(
        source_path, entries_list, include_tests_bool)
    flows_list = []
    for path_info in paths_list:
        flow_info = read_reference_flow(path_info)
        flow_info.script_name = (path_info.relative_to(source_path.resolve())
                                 .as_posix() if source_path.is_dir()
                                 else path_info.name)
        notes_list.extend(f"{flow_info.script_name}:{note_info.line}: "
                          f"{note_info.message}"
                          for note_info in flow_info.notes)
        flows_list.append(flow_info)
    apply_flow_overrides_none(flows_list, overrides_path)
    return flows_list, notes_list


def apply_flow_overrides_none(
    flows_list: list[Flow], overrides_path: Path | None,
) -> None:
    """Apply user wording after resolving the source identities of steps.

    Args:
        flows_list: Flows to label or group.
        overrides_path: TOML context, or None.
    Returns:
        None: Updates presentation without changing source evidence.
    Warnings:
        User titles are context, not inferred business semantics.
    """
    from flowblueprint.cli import apply_overrides_none
    from flowblueprint.summary import apply_groups_list
    import tomllib

    if overrides_path is None:
        return
    settings_dict = tomllib.loads(overrides_path.read_text("utf-8"))
    for flow_info in flows_list:
        if settings_dict.get("groups"):
            flow_info.items = apply_groups_list(
                flow_info.items, settings_dict["groups"])
        apply_overrides_none(flow_info.items, settings_dict.get("blocks", {}))
