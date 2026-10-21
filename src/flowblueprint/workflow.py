"""Write a modular draft and its architecture into one new bundle."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import tempfile

from funcloom import (
    ModularReport, ProjectReport, RefineOptions, modularize_project_report,
    modularize_report,
)

from flowblueprint.drawio import render_drawio_pages_str
from flowblueprint.png import render_png_bytes
from flowblueprint.png_metadata import add_drawio_to_png_bytes
from flowblueprint.reference import (
    apply_flow_overrides_none, read_reference_flows_tuple,
    select_entry_paths_list,
)
from flowblueprint.reference_layout import build_reference_pages_list
from flowblueprint.svg import render_svg_str
from flowblueprint.workflow_flow import expand_workflow_flows_list
from flowblueprint.model import Flow
from flowblueprint.workflow_review import (
    refactor_workflow_dict, write_workflow_review_none,
)
from flowblueprint.workflow_details import write_function_details_list


class WorkflowRefusedError(ValueError):
    """The source cannot be modularized under the current contract."""


def validate_destination_path(source_path: Path, output_path: Path) -> Path:
    """Validate a new bundle outside the source repository.

    Args:
        source_path: Existing script, notebook, or repository.
        output_path: New directory for all workflow artifacts.
    Returns:
        Path: Resolved destination.
    Warnings:
        Existing directories, including empty ones, are refused.
    """
    if output_path.exists() or output_path.is_symlink():
        raise ValueError(f"Output already exists: {output_path}")
    output_path = output_path.resolve()
    source_path = source_path.resolve()
    if not source_path.exists():
        raise ValueError(f"Input does not exist: {source_path}")
    if source_path.is_dir() and output_path.is_relative_to(source_path):
        raise ValueError("The output bundle must be outside the input repo")
    return output_path


def draft_project_report(
    source_path: Path, project_path: Path, entries_list: list[str] | None,
    externalize_sql_bool: bool,
) -> ModularReport | ProjectReport:
    """Call FuncLoom's public API with the selected drafting options.

    Args:
        source_path: Input script, notebook, or repository.
        project_path: Destination for the modular copy.
        entries_list: Optional relative entry paths for a repository.
        externalize_sql_bool: Move supported queries into SQL resources.
    Returns:
        ModularReport | ProjectReport: Written draft or located refusal.
    Warnings:
        Some project entries may be retained after individual refusals.
    """
    options_info = RefineOptions(document=True,
                                 externalize_sql=externalize_sql_bool,
                                 complete_docstrings=True)
    if source_path.is_dir():
        report_info = modularize_project_report(
            source_path, project_path, entries_list=entries_list,
            options_info=options_info)
    else:
        if entries_list:
            raise ValueError("--entry requires a project folder")
        report_info = modularize_report(
            source_path=source_path, output_dir=project_path,
            package_name="src", options_info=options_info)
    if report_info.status != "written":
        details_str = "; ".join(
            f"{info.code} {info.path}:{info.line}: {info.message}"
            for info in report_info.diagnostics)
        raise WorkflowRefusedError(details_str or "Modularization refused")
    return report_info


def clean_report_dict(
    report_info: ModularReport | ProjectReport, final_project_path: Path,
) -> dict:
    """Serialize provenance without embedding source contents or temp paths.

    Args:
        report_info: FuncLoom's result.
        final_project_path: Published local destination of the copy.
    Returns:
        dict: Serializable report with located refusals preserved.
    Warnings:
        No claim of verified runtime equivalence is added.
    """
    report_dict = asdict(report_info)
    report_dict.pop("newlines", None)
    for entry_dict in [report_dict, *report_dict.get("entries", [])]:
        if entry_dict.get("output_dir"):
            entry_dict["output_dir"] = str(final_project_path)
        for file_dict in entry_dict.get("files", []):
            file_dict.pop("text", None)
    return report_dict


def write_architecture_none(
    staging_path: Path, flows_list: list[Flow], title_str: str,
    max_blocks_int: int, group_size_int: int, png_bool: bool,
    detailed_list: list[Flow],
) -> None:
    """Write two editable levels and an optional editable PNG.

    Args:
        staging_path: Private bundle under construction.
        flows_list: Flows read from the generated project.
        title_str: Stable source name.
        max_blocks_int: Column size target.
        group_size_int: Summary grouping size.
        png_bool: Also render the implementation canvas as a PNG.
        detailed_list: Flows with recorded generated steps expanded.
    Returns:
        None: Writes only into the staging directory.
    Warnings:
        Missing optional PNG support prevents the bundle from completing.
    """
    pages_list = build_reference_pages_list(
        flows_list, title_str, "summary", max_blocks_int, group_size_int)
    pages_list += build_reference_pages_list(
        detailed_list, title_str, "detailed", max_blocks_int, group_size_int)
    xml_str = render_drawio_pages_str(pages_list)
    (staging_path / "architecture.drawio").write_text(xml_str, "utf-8")
    for name_str, page_info in zip(("high_level", "detailed"), pages_list):
        (staging_path / f"{name_str}.drawio").write_text(
            render_drawio_pages_str([page_info]), "utf-8")
    if png_bool:
        png_bytes = render_png_bytes(render_svg_str(pages_list[-1]))
        (staging_path / "architecture.drawio.png").write_bytes(
            add_drawio_to_png_bytes(
                png_bytes, render_drawio_pages_str([pages_list[-1]])))


def build_workflow_record_dict(
    report_info: ModularReport | ProjectReport, project_path: Path,
    output_path: Path, notes_list: list[str],
) -> dict:
    """Record conversion coverage and hashes of diagrammed source files.

    Args:
        report_info: Drafting evidence.
        project_path: Staged project to hash.
        output_path: Final bundle directory.
        notes_list: File-qualified diagram limitations.
    Returns:
        dict: A workflow-1 record with explicit review status.
    Warnings:
        Hashes tie diagrams to files; they do not verify their behaviour.
    """
    entries_list = (report_info.entries if isinstance(
        report_info, ProjectReport) else [report_info])
    written_int = sum(info.status == "written" for info in entries_list)
    coverage_str = ("copied_only" if not written_int else
                    "complete" if written_int == len(entries_list)
                    else "partial")
    hashes_dict = {
        path_info.relative_to(project_path).as_posix(): sha256(
            path_info.read_bytes()).hexdigest()
        for path_info in sorted(project_path.rglob("*"))
        if path_info.is_file() and path_info.suffix in (
            ".py", ".ipynb", ".sql")
    }
    return {
        "schema_version": "workflow-1", "status": "draft_for_review",
        "modularization": coverage_str, "source_execution": False,
        "original_source_changed": False, "behavior_verified": False,
        "review_required": True, "diagram_source": "project",
        "generated_source_sha256": hashes_dict,
        "modularization_report": clean_report_dict(
            report_info, output_path / "project"),
        "diagram_notes": notes_list,
    }


def prepare_workflow_dict(
    source_path: Path, output_path: Path,
    entries_list: list[str] | None = None, externalize_sql_bool: bool = False,
    png_bool: bool = False, max_blocks_int: int = 10,
    group_size_int: int = 4, overrides_path: Path | None = None,
    refactor_bool: bool = False,
) -> dict:
    """Create a modular copy, draw it, then finish the local bundle.
    Args:
        source_path: Input repository, script, or notebook.
        output_path: New bundle directory outside an input repository.
        entries_list: Optional relative project entries.
        externalize_sql_bool: Extract supported SQL literals.
        png_bool: Add an editable PNG of the implementation canvas.
        max_blocks_int: Column size target.
        group_size_int: Operations per summary block.
        overrides_path: Optional domain wording for diagram blocks.
        refactor_bool: Run RefacTrail on the copy before drawing.
    Returns:
        dict: Coverage, hashes, source evidence, and limitations.
    Warnings:
        Originals are never executed. A partial conversion remains partial.
    """
    output_path = validate_destination_path(source_path, output_path)
    entries_list = find_workflow_entries_list(source_path, entries_list)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
            prefix=".flowblueprint-", dir=output_path.parent) as folder_str:
        staging_path = Path(folder_str)
        project_path = staging_path / "project"
        report_info = draft_project_report(
            source_path, project_path, entries_list, externalize_sql_bool)
        refactoring_dict = (refactor_workflow_dict(staging_path)
                            if refactor_bool else None)
        record_dict = finish_workflow_dict(
            staging_path, source_path, output_path, entries_list, report_info,
            refactoring_dict, png_bool, max_blocks_int, group_size_int,
            overrides_path)
        publish_staging_none(staging_path, output_path)
    return record_dict


def publish_staging_none(staging_path: Path, output_path: Path) -> None:
    """Move the finished bundle from its staging folder into place.

    Args:
        staging_path: Completed temporary bundle.
        output_path: Final destination, which must still not exist.
    Returns:
        None: Renames the staging folder.
    Warnings:
        Refuses when the destination appeared meanwhile or the staging
        folder is not beside it.
    """
    if output_path.exists() or output_path.is_symlink():
        raise ValueError(f"Output appeared during drafting: {output_path}")
    if staging_path.resolve().parent != output_path.parent:
        raise ValueError("Staging path left the destination parent")
    staging_path.rename(output_path)


def find_workflow_entries_list(
    source_path: Path, entries_list: list[str] | None,
) -> list[str] | None:
    """Select source entries before generated launchers are introduced.

    Args:
        source_path: Input script or repository.
        entries_list: User-selected entries, or automatic detection.
    Returns:
        list[str] | None: Relative source entries for folder conversion.
    Warnings:
        Folder notebooks must be modularized individually at present.
    """
    if not source_path.is_dir():
        return entries_list
    paths_list, _ = select_entry_paths_list(source_path, entries_list)
    if any(path_info.suffix == ".ipynb" for path_info in paths_list):
        raise ValueError("Pass notebooks individually to modularize them")
    return [path_info.relative_to(source_path.resolve()).as_posix()
            for path_info in paths_list]


def add_refactoring_evidence_none(
    staging_path: Path, record_dict: dict, refactoring_dict: dict,
    max_blocks_int: int,
) -> None:
    """Record RefacTrail's results, function details and the review page.

    Args:
        staging_path: Temporary bundle under construction.
        record_dict: Workflow record, updated in place.
        refactoring_dict: RefacTrail evidence.
        max_blocks_int: Diagram column size target.
    Returns:
        None: Writes the detail pages and review.md.
    Warnings:
        Function detail pages show declarations, not dynamic execution.
    """
    record_dict["refactoring"] = refactoring_dict
    record_dict["function_detail_notes"] = write_function_details_list(
        staging_path, refactoring_dict["files"], max_blocks_int)
    write_workflow_review_none(staging_path, record_dict)


def finish_workflow_dict(
    staging_path: Path, source_path: Path, output_path: Path,
    entries_list: list[str] | None,
    report_info: ModularReport | ProjectReport,
    refactoring_dict: dict | None, png_bool: bool, max_blocks_int: int,
    group_size_int: int, overrides_path: Path | None,
) -> dict:
    """Draw final source and write evidence before publishing the local copy.

    Args:
        staging_path: Temporary bundle under construction.
        source_path: Original input used to title the drawings.
        output_path: Final destination for portable report links.
        entries_list: Selected entry paths.
        report_info: FuncLoom conversion evidence.
        refactoring_dict: RefacTrail evidence, when enabled.
        png_bool: Whether to include an editable PNG.
        max_blocks_int: Diagram column size target.
        group_size_int: Summary group size.
        overrides_path: Optional user diagram descriptions.
    Returns:
        dict: Completed source hashes, coverage and remaining work.
    Warnings:
        Function detail pages show declarations, not dynamic execution.
    """
    project_path = staging_path / "project"
    drawn_entries = entries_list if source_path.is_dir() else ["main.py"]
    flows_list, notes_list = read_reference_flows_tuple(
        project_path, drawn_entries)
    detailed_list = expand_workflow_flows_list(
        flows_list, report_info, project_path, notes_list)
    apply_flow_overrides_none(
        [*flows_list, *detailed_list], overrides_path)
    write_architecture_none(staging_path, flows_list, source_path.name,
                            max_blocks_int, group_size_int, png_bool,
                            detailed_list)
    return write_workflow_record_dict(
        staging_path, report_info, output_path, notes_list,
        refactoring_dict, max_blocks_int)


def write_workflow_record_dict(
    staging_path: Path, report_info: ModularReport | ProjectReport,
    output_path: Path, notes_list: list[str],
    refactoring_dict: dict | None, max_blocks_int: int,
) -> dict:
    """Build the workflow record and write it as workflow.json.

    Args:
        staging_path: Temporary bundle under construction.
        report_info: FuncLoom conversion evidence.
        output_path: Final destination for portable report links.
        notes_list: Drawing limitations.
        refactoring_dict: RefacTrail evidence, when enabled.
        max_blocks_int: Diagram column size target.
    Returns:
        dict: Completed source hashes, coverage and remaining work.
    Warnings:
        None.
    """
    project_path = staging_path / "project"
    record_dict = build_workflow_record_dict(
        report_info, project_path, output_path, notes_list)
    if refactoring_dict is not None:
        add_refactoring_evidence_none(staging_path, record_dict,
                                      refactoring_dict, max_blocks_int)
    (staging_path / "workflow.json").write_text(
        json.dumps(record_dict, indent=2) + "\n", "utf-8")
    return record_dict
