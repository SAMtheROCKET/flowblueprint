"""Expand only steps recorded by the current FuncLoom drafting operation."""

import ast
from copy import deepcopy
from pathlib import Path

from funcloom import ModularReport, ProjectReport

from flowblueprint.flow import FlowBuilder
from flowblueprint.model import (
    Branch, Flow, Item, Loop, Step, Port, Source, DATA_KIND, PROCESS_KIND,
)
from flowblueprint.source import ScriptInfo, load_script


def build_recorded_step_flows_dict(
    entry_info: ModularReport, project_path: Path,
) -> dict[tuple[str, str], Flow]:
    """Resolve generated step identities using the current draft report.

    Args:
        entry_info: Written entry and its recorded generated functions.
        project_path: The newly generated project directory.
    Returns:
        dict: (module basename, function name) to declared step body.
    Warnings:
        Only recorded steps are expanded; arbitrary helper calls are not.
    """
    names_set = {info.name for info in entry_info.steps}
    bodies_dict = {}
    for file_info in entry_info.files:
        path_info = project_path / file_info.path
        if path_info.suffix != ".py":
            continue
        source_info = load_script(path_info)
        for name_str in names_set.intersection(source_info.functions):
            builder_info = FlowBuilder(source_info)
            function_info = source_info.functions[name_str]
            body_info = builder_info.build_function_flow(
                function_info, file_info.path)
            bodies_dict[(path_info.name, name_str)] = body_info
    return bodies_dict


def expand_nested_items_none(
    item_info: Item, bodies_dict: dict[tuple[str, str], Flow],
    notes_list: list[str], entry_str: str,
) -> None:
    """Expand the items inside a loop body or both paths of a branch.

    Args:
        item_info: A loop, branch or step (steps are left alone).
        bodies_dict: Report-backed generated step bodies.
        notes_list: Receives source-qualified limitations.
        entry_str: Entry path for notes.
    Returns:
        None: Replaces the nested item lists in place.
    Warnings:
        None.
    """
    if isinstance(item_info, Loop):
        item_info.body = expand_recorded_items_list(
            item_info.body, bodies_dict, notes_list, entry_str)
    elif isinstance(item_info, Branch):
        item_info.yes = expand_recorded_items_list(
            item_info.yes, bodies_dict, notes_list, entry_str)
        item_info.no = expand_recorded_items_list(
            item_info.no, bodies_dict, notes_list, entry_str)


def expand_recorded_items_list(
    items_list: list[Item], bodies_dict: dict[tuple[str, str], Flow],
    notes_list: list[str], entry_str: str,
) -> list[Item]:
    """Expose operations inside generated steps while preserving boundaries.

    Args:
        items_list: Copied entry operations.
        bodies_dict: Report-backed generated step bodies.
        notes_list: Receives source-qualified limitations.
        entry_str: Entry path for notes.
    Returns:
        list[Item]: Entry calls followed by their declared step operations.
    Warnings:
        Definitions and callbacks are never treated as executed bodies.
    """
    expanded_list = []
    for item_info in items_list:
        expand_nested_items_none(item_info, bodies_dict, notes_list,
                                 entry_str)
        expanded_list.append(item_info)
        if not isinstance(item_info, Step):
            continue
        body_info = bodies_dict.get((item_info.module, item_info.title))
        if body_info is None:
            continue
        item_info.description += " Declared step body follows."
        expanded_list.extend(deepcopy(body_info.items))
        notes_list.extend(f"{body_info.script_name}:{note.line}: "
                          f"{note.message}" for note in body_info.notes)
        if not body_info.items:
            item_info.description = (
                "No operations expanded before return; "
                "see the generated function body.")
            notes_list.append(f"{entry_str}: {item_info.title}: "
                              "returned callables and dynamic dispatch "
                              "are not expanded as runtime execution.")
    return expanded_list


def expand_workflow_flows_list(
    flows_list: list[Flow], report_info: ModularReport | ProjectReport,
    project_path: Path, notes_list: list[str],
) -> list[Flow]:
    """Show generated step implementations using per-entry provenance.

    Args:
        flows_list: Entry flows of the generated project.
        report_info: The report that produced this project.
        project_path: Location of the generated sources.
        notes_list: Destination for remaining unresolved effects.
    Returns:
        list[Flow]: Detailed flows; the originals remain available.
    Warnings:
        A refused or unconverted entry keeps its original static view.
    """
    entries_list = (report_info.entries if isinstance(
        report_info, ProjectReport) else [report_info])
    detailed_list = deepcopy(flows_list)
    for flow_info in detailed_list:
        entry_info = next((entry for entry in entries_list
                           if entry.status == "written" and any(
                               info.path == flow_info.script_name
                               for info in entry.files)), None)
        if entry_info is None:
            continue
        bodies_dict = build_recorded_step_flows_dict(entry_info, project_path)
        flow_info.items = expand_recorded_items_list(
            flow_info.items, bodies_dict, notes_list, flow_info.script_name)
        configuration_info = build_configuration_step(entry_info, project_path)
        if configuration_info is not None:
            flow_info.items.insert(0, configuration_info)
            flow_info.modules.append(configuration_info.module)
        flow_info.modules = sorted(set(flow_info.modules).union(
            module_str for body in bodies_dict.values()
            for module_str in body.modules))
    return detailed_list


def build_configuration_step(
    entry_info: ModularReport, project_path: Path,
) -> Step | None:
    """Show constants and query assets initialized by generated modules.

    Args:
        entry_info: Recorded constant relocations for this entry.
        project_path: Written generated project.
    Returns:
        Step | None: A configuration block with file and query inputs.
    Warnings:
        Types and import-time behaviour remain unverified.
    """
    names_set = set(entry_info.constants.values())
    if not names_set:
        return None
    for file_info in entry_info.files:
        if not file_info.path.endswith(".py"):
            continue
        path_info = project_path / file_info.path
        source_info = load_script(path_info)
        assigned_set = {target.id for statement in source_info.tree.body
                        if isinstance(statement, ast.Assign)
                        for target in statement.targets
                        if isinstance(target, ast.Name)}
        if names_set.intersection(assigned_set):
            return make_configuration_step(
                source_info, file_info.path, path_info.name,
                sorted(names_set.intersection(assigned_set)))
    return None


def make_configuration_step(
    source_info: ScriptInfo, path_str: str, module_str: str,
    names_list: list[str],
) -> Step:
    """The configuration block of a generated module's constants.

    Args:
        source_info: The parsed generated module.
        path_str: Its path within the project copy.
        module_str: Its file name, for the block colour.
        names_list: The relocated constants it assigns.
    Returns:
        Step: A block reading the module and the files its constants
            name, producing the constants.
    Warnings:
        Types and import-time behaviour remain unverified.
    """
    items_list = FlowBuilder(source_info).build_items([
        statement for statement in source_info.tree.body
        if isinstance(statement, (ast.Assign, ast.AnnAssign))])
    sources_list = [Source(DATA_KIND, path_str)]
    sources_list.extend(source for item in items_list
                        if isinstance(item, Step)
                        for source in item.sources)
    return Step(
        PROCESS_KIND, "Load configuration",
        "Constants and resources initialized by the generated module.",
        outputs=[Port(name) for name in names_list],
        module=module_str, sources=sources_list)
