"""Command line: ``flowblueprint PATH [options]``.

PATH is a script, a notebook or a project folder. The code is read
without running it. A script's flow goes to ``<script>.drawio`` next to
it, a folder's overview to ``<folder>/architecture.drawio``, or either
to ``--output``, whose suffix picks the format: .drawio (editable),
.svg (image), .html (a page holding the image), .md (Markdown with a
Mermaid flowchart, which GitHub and GitLab render) or .mmd (Mermaid
text). Rule findings and notes are printed. Existing files are never
overwritten unless ``--force`` is given; sources are never changed.
"""

import argparse
from pathlib import Path
import sys
import tomllib

from flowblueprint import __version__
from flowblueprint.drawio import render_drawio_str
from flowblueprint.flow import build_flow
from flowblueprint.layout import layout_flow
from flowblueprint.grouping import choose_group_depth_int, group_project
from flowblueprint.mermaid import render_markdown_str, render_mermaid_str
from flowblueprint.model import Branch, Diagram, Flow, Item, Loop, Step
from flowblueprint.overview import layout_project
from flowblueprint.page import render_html_str
from flowblueprint.png import PngUnavailableError, render_png_bytes
from flowblueprint.project import load_project
from flowblueprint.rules import check_diagram
from flowblueprint.source import load_script
from flowblueprint.svg import render_svg_str
from flowblueprint.summary import apply_groups_list, summarise_items_list

OUTPUT_SUFFIXES_TUPLE = (".drawio", ".svg", ".png", ".html", ".md",
                         ".mmd")
# Mermaid places shapes itself, so its flows are laid out in one column.
MERMAID_SUFFIXES_TUPLE = (".md", ".mmd")
SINGLE_COLUMN_BLOCKS_INT = 1_000_000


def build_parser() -> argparse.ArgumentParser:
    """The argument parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="flowblueprint",
        description="Turn a Python script, notebook or project folder "
                    "into a block-diagram architecture without running "
                    "it.")
    parser.add_argument("script", type=Path, metavar="PATH",
                        help="a .py script, an .ipynb notebook or a "
                             "project folder")
    parser.add_argument("-o", "--output", type=Path,
                        help="output file: .drawio (editable, the default),"
                             " .svg or .png (image), .html (web page), .md "
                             "(Markdown with Mermaid) or .mmd (Mermaid)")
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
    parser.add_argument("--version", action="version",
                        version=f"flowblueprint {__version__}")
    add_check_options_none(parser)
    add_folder_options_none(parser)
    return parser


def add_check_options_none(parser: argparse.ArgumentParser) -> None:
    """Add the options that check instead of writing.

    Args:
        parser: The parser (changed in place).

    Returns:
        None.
    """
    parser.add_argument("--check", action="store_true",
                        help="only check; exit 1 on rule errors")
    parser.add_argument("--up-to-date", action="store_true",
                        help="write nothing; exit 1 when the output file "
                             "is missing or differs from a fresh drawing "
                             "(for CI)")


def add_folder_options_none(parser: argparse.ArgumentParser) -> None:
    """Add the options that apply to project folders.

    Args:
        parser: The parser (changed in place).

    Returns:
        None.
    """
    parser.add_argument("--include-tests", action="store_true",
                        help="folders: also draw test files and folders")
    parser.add_argument("--group-depth", type=int, default=None,
                        help="folders: one block per sub-package this many "
                             "folders deep (default: automatic above 40 "
                             "files; 0: one block per file)")


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


def render_output_str(output: Path, diagram: Diagram,
                      notes_list: list[str]) -> str:
    """Render a diagram in the format the output suffix names.

    Args:
        output: The output file.
        diagram: The diagram (one column for Mermaid formats).
        notes_list: Lines about what the diagram leaves out.

    Returns:
        The file text (for .png, the SVG it is rasterised from).
    """
    suffix_str = output.suffix.lower()
    if suffix_str in (".svg", ".png"):
        return render_svg_str(diagram)
    if suffix_str == ".html":
        return render_html_str(diagram, notes_list)
    if suffix_str == ".md":
        return render_markdown_str(diagram, notes_list)
    if suffix_str == ".mmd":
        return render_mermaid_str(diagram)
    return render_drawio_str(diagram)


def write_output_int(output: Path, data: str | bytes, force: bool,
                     summary_str: str) -> int:
    """Write the rendered file unless that would overwrite one.

    Args:
        output: The output file.
        data: Its text, or bytes for an image.
        force: Whether an existing file may be replaced.
        summary_str: What was written, for the success message.

    Returns:
        0 when written, 2 when refused.
    """
    if output.exists() and not force:
        print(f"flowblueprint: {output} exists; use --force to replace it",
              file=sys.stderr)
        return 2
    if isinstance(data, bytes):
        output.write_bytes(data)
    else:
        output.write_text(data, encoding="utf-8")
    print(f"wrote {output} ({summary_str})")
    return 0


def compare_output_int(output: Path, data: str | bytes) -> int:
    """Report whether a saved diagram matches a fresh drawing.

    Args:
        output: The saved diagram file.
        data: The freshly rendered text, or bytes for an image.

    Returns:
        0 when the file is up to date, 1 when it is missing or differs.
    """
    try:
        current_str = (output.read_bytes() if isinstance(data, bytes)
                       else output.read_text(encoding="utf-8"))
    except FileNotFoundError:
        current_str = None
    if current_str == data:
        print(f"{output} is up to date")
        return 0
    state_str = "is missing" if current_str is None else "is out of date"
    print(f"flowblueprint: {output} {state_str}; redraw it with --force",
          file=sys.stderr)
    return 1


def finish_output_int(arguments: argparse.Namespace, output: Path,
                      text_str: str, summary_str: str) -> int:
    """Write the drawing, or compare it with the saved file.

    Args:
        arguments: The parsed command line.
        output: The output file.
        text_str: The rendered text.
        summary_str: What was drawn, for the success message.

    Returns:
        The exit code; 2 when PNG output lacks its optional renderer.
    """
    data: str | bytes = text_str
    if output.suffix.lower() == ".png":
        try:
            data = render_png_bytes(text_str)
        except PngUnavailableError as error:
            print(f"flowblueprint: {error}", file=sys.stderr)
            return 2
    if arguments.up_to_date:
        return compare_output_int(output, data)
    return write_output_int(output, data, arguments.force, summary_str)


def check_output_suffix_bool(output: Path | None) -> bool:
    """Whether an output path has a supported suffix.

    Args:
        output: The --output path, or None for the default.

    Returns:
        True when supported; otherwise an error is printed.
    """
    if output is None or output.suffix.lower() in OUTPUT_SUFFIXES_TUPLE:
        return True
    print(f"flowblueprint: unknown output format {output.suffix!r}; use "
          f"one of {', '.join(OUTPUT_SUFFIXES_TUPLE)}", file=sys.stderr)
    return False


def run_project_int(arguments: argparse.Namespace) -> int:
    """Draw a project folder's overview.

    Args:
        arguments: The parsed command line.

    Returns:
        The exit code.
    """
    folder = arguments.script
    project = load_project(folder, arguments.include_tests)
    for note_str in project.notes:
        print(f"{folder}: note: {note_str}")
    if not project.files:
        print(f"flowblueprint: no Python files or notebooks in {folder}",
              file=sys.stderr)
        return 2
    if arguments.check:
        return 0
    depth_int = (choose_group_depth_int(project)
                 if arguments.group_depth is None else arguments.group_depth)
    if depth_int > 0:
        project = group_project(project, depth_int)
        print(f"grouped into {len(project.files)} blocks at folder depth "
              f"{depth_int} (use --group-depth to change)")
    diagram = layout_project(project)
    output = arguments.output or folder / "architecture.drawio"
    return finish_output_int(
        arguments, output,
        render_output_str(output, diagram, project.notes),
        f"{len(project.files)} files, {len(project.edges)} imports")


def main(argv_list: list[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv_list: Arguments (default: sys.argv[1:]).

    Returns:
        0 on success, 1 on rule errors with --check or a stale file with
        --up-to-date, 2 on input errors.
    """
    arguments = build_parser().parse_args(argv_list)
    script = arguments.script
    if not check_output_suffix_bool(arguments.output):
        return 2
    if script.is_dir():
        return run_project_int(arguments)
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
    if output.suffix.lower() in MERMAID_SUFFIXES_TUPLE:
        diagram = layout_flow(flow, SINGLE_COLUMN_BLOCKS_INT)
    notes_list = [f"line {note.line}: {note.message}" for note in flow.notes]
    return finish_output_int(
        arguments, output, render_output_str(output, diagram, notes_list),
        f"{len(diagram.nodes)} shapes, {diagram.column_count} column(s)")


if __name__ == "__main__":
    raise SystemExit(main())
