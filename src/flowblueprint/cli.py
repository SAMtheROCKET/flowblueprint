"""Command line: ``flowblueprint SCRIPT [options]``.

Reads the script without running it, writes ``<script>.drawio`` next to
it (or to ``--output``) and prints rule findings and notes. Existing
files are never overwritten unless ``--force`` is given; the script
itself is never changed.
"""

import argparse
from pathlib import Path
import sys
import tomllib

from flowblueprint import __version__
from flowblueprint.drawio import render_drawio_str
from flowblueprint.flow import build_flow
from flowblueprint.layout import layout_flow
from flowblueprint.model import Branch, Diagram, Flow, Item, Loop, Step
from flowblueprint.rules import check_diagram
from flowblueprint.source import load_script
from flowblueprint.svg import render_svg_str
from flowblueprint.summary import apply_groups_list, summarise_items_list


def build_parser() -> argparse.ArgumentParser:
    """The argument parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="flowblueprint",
        description="Turn a Python script into a block-diagram "
                    "architecture (draw.io) without running it.")
    parser.add_argument("script", type=Path, help="the .py file to draw")
    parser.add_argument("-o", "--output", type=Path,
                        help="output file: .drawio (editable, default next"
                             " to the script) or .svg (image preview)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing output file")
    parser.add_argument("--overrides", type=Path,
                        help="TOML file replacing titles or descriptions "
             "and naming groups of functions to pack")
    parser.add_argument("--level", choices=("detailed", "summary"),
                        default="detailed",
                        help="detailed: one block per call; summary: pack "
                             "consecutive operations into fewer blocks")
    parser.add_argument("--group-size", type=int, default=4,
                        help="most operations per summary block "
                             "(default 4)")
    parser.add_argument("--max-blocks", type=int, default=10,
                        help="most blocks per column (default 10)")
    parser.add_argument("--check", action="store_true",
                        help="only check; exit 1 on rule errors")
    parser.add_argument("--version", action="version",
                        version=f"flowblueprint {__version__}")
    return parser


def apply_overrides_none(items_list: list[Item], blocks_dict: dict) -> None:
    """Replace titles and descriptions named in an override table.

    Args:
        items_list: Items to update in place, nested ones included.
        blocks_dict: Function name or "line:N" -> {"title",
            "description"}.

    Returns:
        None.
    """
    for item in items_list:
        if isinstance(item, Loop):
            apply_overrides_none(item.body, blocks_dict)
        elif isinstance(item, Branch):
            apply_overrides_none(item.yes, blocks_dict)
            apply_overrides_none(item.no, blocks_dict)
        elif isinstance(item, Step):
            entry_dict = (blocks_dict.get(f"line:{item.line}")
                          or blocks_dict.get(item.title) or {})
            item.title = str(entry_dict.get("title", item.title))
            item.description = str(entry_dict.get("description",
                                                  item.description))


def load_flow(script: Path, overrides: Path | None,
              level_str: str = "detailed", group_size_int: int = 4) -> Flow:
    """Read a script and build its flow, with overrides applied.

    Args:
        script: The script.
        overrides: An optional TOML file with a [blocks] table and
            [[groups]] entries.
        level_str: "detailed" or "summary".
        group_size_int: The most operations per summary block.

    Returns:
        The flow. Named groups are packed first, then block overrides
        apply, then the summary level packs the remaining runs.
    """
    flow = build_flow(load_script(script))
    settings_dict: dict = {}
    if overrides is not None:
        with overrides.open("rb") as handle:
            settings_dict = tomllib.load(handle)
    groups_list = settings_dict.get("groups", [])
    if groups_list:
        flow.items = apply_groups_list(flow.items, groups_list)
    apply_overrides_none(flow.items, settings_dict.get("blocks", {}))
    if level_str == "summary":
        flow.items = summarise_items_list(flow.items, group_size_int)
    return flow


def report_findings_bool(script: Path, flow: Flow, diagram: Diagram,
                         max_blocks_int: int) -> bool:
    """Print notes and rule findings.

    Args:
        script: The script, for the location prefix.
        flow: The flow, whose notes list what was not drawn.
        diagram: The laid-out diagram to check.
        max_blocks_int: The column block limit.

    Returns:
        True when any finding is an error.
    """
    findings_list = check_diagram(diagram, max_blocks_int)
    for note in flow.notes:
        print(f"{script}:{note.line}: note: {note.message}")
    for finding in findings_list:
        print(f"{script}:{finding.line}: {finding.code} {finding.severity}: "
              f"{finding.message}")
    return any(finding.severity == "error" for finding in findings_list)


def main(argv_list: list[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv_list: Arguments (default: sys.argv[1:]).

    Returns:
        0 on success, 1 on rule errors with --check, 2 on input errors.
    """
    arguments = build_parser().parse_args(argv_list)
    script = arguments.script
    try:
        flow = load_flow(script, arguments.overrides, arguments.level,
                         arguments.group_size)
    except (OSError, SyntaxError, ValueError,
            tomllib.TOMLDecodeError) as error:
        print(f"flowblueprint: cannot read {script}: {error}",
              file=sys.stderr)
        return 2
    diagram = layout_flow(flow, arguments.max_blocks)
    has_errors = report_findings_bool(script, flow, diagram,
                                      arguments.max_blocks)
    if arguments.check:
        return 1 if has_errors else 0
    output = arguments.output or script.with_suffix(".drawio")
    if output.exists() and not arguments.force:
        print(f"flowblueprint: {output} exists; use --force to replace it",
              file=sys.stderr)
        return 2
    renderer = (render_svg_str if output.suffix.lower() == ".svg"
                else render_drawio_str)
    output.write_text(renderer(diagram), encoding="utf-8")
    print(f"wrote {output} ({len(diagram.nodes)} shapes, "
          f"{diagram.column_count} column(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
