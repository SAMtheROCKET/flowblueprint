"""Thin CLI adapters for operational canvases and modular drafting."""

import argparse
from pathlib import Path
import sys
import tomllib

from flowblueprint.png import PngUnavailableError
from flowblueprint.reference import read_reference_flows_tuple
from flowblueprint.reference_layout import build_reference_pages_list
from flowblueprint.workflow import WorkflowRefusedError, prepare_workflow_dict


def add_reference_options_none(parser_info: argparse.ArgumentParser) -> None:
    """Add explicit reference-view and new-copy workflow options.

    Args:
        parser_info: Existing command parser.
    Returns:
        None: Adds arguments without changing older command defaults.
    Warnings:
        Drafting is enabled only by --modularize-to.
    """
    parser_info.add_argument(
        "--view", choices=("pages", "reference"), default="pages",
        help="reference: operational scripts side by side, with two levels")
    parser_info.add_argument(
        "--entry", action="append", help="relative entry path; repeatable")
    parser_info.add_argument(
        "--modularize-to", type=Path, metavar="NEW_DIR",
        help="write a modular copy and both architecture levels in NEW_DIR")
    parser_info.add_argument(
        "--pipeline-to", type=Path, metavar="NEW_DIR",
        help="run FuncLoom, RefacTrail and FlowBlueprint in one new bundle")
    parser_info.add_argument(
        "--externalize-sql", action="store_true",
        help="with --modularize-to, extract supported SQL into .sql files")
    parser_info.add_argument(
        "--png", action="store_true",
        help="with --modularize-to, include an editable architecture PNG")


def validate_reference_arguments_none(
    arguments_info: argparse.Namespace,
) -> None:
    """Reject incompatible options before any workflow writes.

    Args:
        arguments_info: Parsed command arguments.
    Returns:
        None: Raises ValueError on conflicting or unused flags.
    Warnings:
        --force never permits overwriting a workflow bundle.
    """
    if arguments_info.pipeline_to:
        if arguments_info.modularize_to:
            raise ValueError("Choose --pipeline-to or --modularize-to")
        arguments_info.modularize_to = arguments_info.pipeline_to
    if arguments_info.modularize_to:
        if (arguments_info.output or arguments_info.check
                or arguments_info.up_to_date or arguments_info.force
                or arguments_info.level != "full"
                or arguments_info.group_depth is not None
                or arguments_info.include_tests):
            raise ValueError("--modularize-to writes a new bundle with both "
                             "levels; omit --output, --check, --up-to-date, "
                             "--force, --level, --group-depth, "
                             "--include-tests")
    elif arguments_info.png or arguments_info.externalize_sql:
        raise ValueError("--png and --externalize-sql need --modularize-to")
    elif arguments_info.entry and arguments_info.view != "reference":
        raise ValueError("--entry needs --view reference or --modularize-to")
    if arguments_info.view == "reference" and (
            arguments_info.group_depth is not None):
        raise ValueError("--group-depth applies to the pages view only")


def run_reference_int(arguments_info: argparse.Namespace) -> int:
    """Draw the operational view with existing output and check contracts.

    Args:
        arguments_info: Parsed drawing options.
    Returns:
        int: Existing CLI success, finding, or usage status.
    Warnings:
        Unknown types, source omissions and dispatch remain unverified.
    """
    from flowblueprint.cli import (
        finish_output_int, render_pages_str, report_findings_bool,
    )

    source_path = arguments_info.script
    flows_list, notes_list = read_reference_flows_tuple(
        source_path, arguments_info.entry, arguments_info.include_tests,
        arguments_info.overrides)
    output_path = arguments_info.output or (
        source_path / "architecture.drawio" if source_path.is_dir()
        else source_path.with_suffix(".drawio"))
    max_blocks_int = (1_000_000 if output_path.suffix in (".md", ".mmd")
                      else arguments_info.max_blocks)
    pages_list = build_reference_pages_list(
        flows_list, source_path.name, arguments_info.level,
        max_blocks_int, arguments_info.group_size)
    errors_bool = report_findings_bool(
        source_path, flows_list, pages_list, max_blocks_int,
        arguments_info.verbose)
    for note_str in notes_list:
        print(f"note: {note_str}")
    if arguments_info.check:
        return 1 if errors_bool else 0
    return finish_output_int(
        arguments_info, output_path,
        render_pages_str(output_path, pages_list, notes_list),
        f"{len(flows_list)} entry flows, {len(pages_list)} reference canvases",
        pages_list)


def run_modularize_to_int(arguments_info: argparse.Namespace) -> int:
    """Run --modularize-to (and --pipeline-to) and print the outcome.

    Args:
        arguments_info: Parsed command arguments.
    Returns:
        int: 0 when modularization is complete (and, with --pipeline-to,
            RefacTrail passed); 1 otherwise.
    Warnings:
        Errors are raised for dispatch_reference_int to report.
    """
    record_dict = prepare_workflow_dict(
        arguments_info.script, arguments_info.modularize_to,
        arguments_info.entry, arguments_info.externalize_sql,
        arguments_info.png, arguments_info.max_blocks,
        arguments_info.group_size, arguments_info.overrides,
        refactor_bool=bool(arguments_info.pipeline_to))
    coverage_str = record_dict["modularization"]
    print(f"wrote {arguments_info.modularize_to}; "
          f"modularization={coverage_str}; review required; "
          "behavior_verified=false. See workflow.json.")
    if arguments_info.pipeline_to:
        report_dict = record_dict["refactoring"]
        print(f"RefacTrail: {report_dict['status']}; "
              f"{len(report_dict['findings'])} findings remain. "
              "See review.md and context-questions.json.")
        return int(coverage_str != "complete" or
                   report_dict["status"] != "passed")
    return 0 if coverage_str == "complete" else 1


def dispatch_reference_int(arguments_info: argparse.Namespace) -> int | None:
    """Handle the new modes while leaving the original pages mode intact.

    Args:
        arguments_info: Parsed command arguments.
    Returns:
        int | None: Exit status, or None to use the original drawing path.
    Warnings:
        Partial modularization returns 1 with a reviewable bundle.
    """
    try:
        validate_reference_arguments_none(arguments_info)
        if arguments_info.modularize_to:
            return run_modularize_to_int(arguments_info)
        if arguments_info.view == "reference":
            return run_reference_int(arguments_info)
        return None
    except WorkflowRefusedError as error_info:
        print(f"flowblueprint: refused: {error_info}", file=sys.stderr)
        return 1
    except (OSError, ValueError, SyntaxError, PngUnavailableError,
            tomllib.TOMLDecodeError) as error_info:
        print(f"flowblueprint: {error_info}", file=sys.stderr)
        return 2
