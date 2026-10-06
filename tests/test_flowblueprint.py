"""Regression tests for FlowBlueprint (standard-library unittest)."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET

from flowblueprint.cli import main
from flowblueprint.drawio import render_drawio_str
from flowblueprint.flow import build_flow
from flowblueprint.layout import layout_flow
from flowblueprint.model import (
    CONNECTOR_KIND, DATABASE_KIND, DATA_KIND, DOCUMENT_KIND, LEGEND_KIND,
    LOOP_CLOSE_KIND, LOOP_OPEN_KIND, PLOT_KIND, Branch, Loop)
from flowblueprint.rules import check_diagram
from flowblueprint.source import load_script
from flowblueprint.summary import apply_groups_list, summarise_items_list
from flowblueprint.svg import render_svg_str
from flowblueprint.mermaid import render_mermaid_str
from flowblueprint.overview import layout_project
from flowblueprint.page import render_html_str
from flowblueprint.project import (
    ENTRY_KIND, MODULE_KIND, NOTEBOOK_KIND, PACKAGE_KIND, load_project)

EXAMPLES = Path(__file__).parent / "examples"


def flow_of(source_str: str, extra_dict: dict | None = None):
    """Build the flow of a script written to a temporary folder."""
    folder = Path(tempfile.mkdtemp())
    for name_str, text_str in (extra_dict or {}).items():
        (folder / name_str).write_text(textwrap.dedent(text_str),
                                       encoding="utf-8")
    path = folder / "script.py"
    path.write_text(textwrap.dedent(source_str), encoding="utf-8")
    return build_flow(load_script(path))


def edges_by_label(diagram) -> list[tuple[str, str, str]]:
    """(source first label line, target first label line, edge label)."""
    nodes = {node.node_id: node for node in diagram.nodes}
    return [(" ".join(nodes[edge.source_id].label),
             " ".join(nodes[edge.target_id].label), edge.label)
            for edge in diagram.edges]


class EntryPointTests(unittest.TestCase):
    def test_main_guard_calling_main_uses_main_body(self):
        flow = flow_of("""
            def load_rows(): ...
            def main():
                rows = load_rows()
            if __name__ == "__main__":
                main()
        """)
        self.assertEqual([item.title for item in flow.items], ["load_rows"])

    def test_module_level_script_without_main(self):
        flow = flow_of("""
            import pandas as pd
            def clean(df): ...
            raw_df = pd.read_csv("data/raw.csv")
            clean_df = clean(raw_df)
        """)
        self.assertEqual(len(flow.items), 2)
        self.assertEqual(flow.items[0].sources[0].label, "raw.csv")
        self.assertEqual(flow.items[1].outputs[0].dtype, "DataFrame")

    def test_source_is_never_executed(self):
        flow = flow_of("""
            raise SystemExit("this must not run")
            def f(): ...
        """)
        self.assertEqual(flow.script_name, "script.py")


class StepTests(unittest.TestCase):
    def test_docstring_annotations_and_tuple_returns(self):
        flow = flow_of("""
            def split_rows(rows: list[int]) -> tuple[list, int]:
                '''Split the rows into kept rows and a count.

                More text that is not shown.
                '''
            def main():
                kept_list, count = split_rows(rows)
        """)
        step = flow.items[0]
        self.assertEqual(step.description,
                         "Split the rows into kept rows and a count.")
        self.assertEqual(step.inputs[0].dtype, "list[int]")
        self.assertEqual([port.dtype for port in step.outputs],
                         ["list", "int"])

    def test_name_based_description_and_unknown_types(self):
        flow = flow_of("""
            def calculate_distance(a, b): ...
            def main():
                result = calculate_distance(x, y)
        """)
        step = flow.items[0]
        self.assertEqual(step.description, "Calculate distance.")
        self.assertEqual(step.inputs[0].dtype, "unknown")

    def test_developed_module_is_coloured_and_described(self):
        flow = flow_of("""
            from helpers import scale_values
            def main():
                scaled_arr = scale_values(values_arr)
        """, {"helpers.py": '''
            def scale_values(values):
                """Scale values to the unit range."""
        '''})
        self.assertEqual(flow.modules, ["helpers.py"])
        self.assertEqual(flow.items[0].module, "helpers.py")
        self.assertEqual(flow.items[0].description,
                         "Scale values to the unit range.")

    def test_installed_module_calls_are_not_titled(self):
        flow = flow_of("""
            import numpy as np
            def main():
                total = np.sum(values)
                count_int = 3
        """)
        self.assertEqual(len(flow.items), 1)
        self.assertEqual(flow.items[0].title, "")

    def test_plain_statements_are_grouped(self):
        flow = flow_of("""
            def main():
                a_int = 1
                b_list = []
                b_list.append(a_int)
                a_int += 2
                c = 5
        """)
        self.assertEqual(len(flow.items), 1)
        self.assertEqual(flow.items[0].description,
                         "Set a_int; set b_list; append a_int to b_list; "
                         "and 2 more.")

    def test_pipe_chain_becomes_one_step_per_function(self):
        flow = flow_of("""
            def drop_bad(df): ...
            def add_total(df, column): ...
            def main():
                result_df = raw_df.pipe(drop_bad).pipe(add_total, "x")
        """)
        self.assertEqual([item.title for item in flow.items],
                         ["drop_bad", "add_total"])
        self.assertEqual(flow.items[1].outputs[0].name, "result_df")


class ClassAndLevelTests(unittest.TestCase):
    OOP_SOURCE = """
        class ReportPipeline:
            '''Monthly sales report pipeline.'''

            def __init__(self, folder_str: str):
                self.folder_str = folder_str

            def load_orders(self) -> list[dict]:
                '''Load the orders of the month.'''

            def total_by_region(self, orders: list[dict]) -> dict:
                '''Add up the order values per region.'''

            def run(self):
                '''Run every stage.'''
                orders = self.load_orders()
                totals = self.total_by_region(orders)
                self.save_totals(totals)

            def save_totals(self, totals: dict) -> None:
                '''Write the totals table.'''

        if __name__ == "__main__":
            ReportPipeline("data").run()
    """

    def test_single_hand_over_method_is_expanded(self):
        flow = flow_of(self.OOP_SOURCE)
        self.assertEqual([item.title for item in flow.items],
                         ["load_orders", "total_by_region", "save_totals"])
        self.assertEqual(flow.items[0].outputs[0].dtype, "list[dict]")
        self.assertEqual(flow.items[1].description,
                         "Add up the order values per region.")

    def test_instances_and_constructors_resolve(self):
        flow = flow_of("""
            from shapes import Grid
            def main():
                grid = Grid(10)
                grid.fill_cells(3)
                grid.render()
        """, {"shapes.py": '''
            class Grid:
                """A square grid of cells."""
                def __init__(self, size_int: int): ...
                def fill_cells(self, count_int: int):
                    """Fill random cells."""
                def render(self):
                    """Draw the grid."""
        '''})
        self.assertEqual([item.title for item in flow.items],
                         ["Grid", "fill_cells", "render"])
        self.assertEqual(flow.items[0].description,
                         "Create the Grid: A square grid of cells.")
        self.assertEqual(flow.items[0].outputs[0].dtype, "Grid")
        self.assertEqual(flow.modules, ["shapes.py"])
        self.assertEqual(flow.items[1].inputs[0].dtype, "int")

    def test_summary_level_packs_operations(self):
        flow = build_flow(load_script(EXAMPLES / "station_report.py"))
        loop = flow.items[2]
        packed = summarise_items_list(flow.items, 3)
        first = packed[1].body[0]
        self.assertTrue(first.packed)
        self.assertEqual(first.title, "Load, repair and flag")
        self.assertEqual([port.name for port in first.inputs],
                         ["station_str", "folder_str", "threshold_float"])
        self.assertEqual([port.name for port in first.outputs],
                         ["flagged_df", "event_count_int"])
        self.assertIs(loop, packed[1])

    def test_named_groups_pack_listed_functions(self):
        flow = build_flow(load_script(EXAMPLES / "station_report.py"))
        groups = [{"title": "prepare_readings",
                   "description": "Load and clean one station.",
                   "functions": ["load_station_readings",
                                 "repair_missing_values"]}]
        loop = apply_groups_list(flow.items, groups)[2]
        self.assertEqual(loop.body[0].title, "prepare_readings")
        self.assertEqual(loop.body[1].title, "flag_heat_events")
        summary = summarise_items_list([loop], 4)[0]
        self.assertEqual(summary.body[0].title, "prepare_readings")


class SourceShapeTests(unittest.TestCase):
    def test_database_storage_and_document_shapes(self):
        flow = flow_of("""
            import pandas as pd
            import matplotlib.pyplot as plt
            def main():
                rows_df = pd.read_sql("select * from t", engine)
                cloud_df = pd.read_parquet("s3://bucket/data.parquet")
                plt.plot(rows_df.x)
                plt.savefig("figure.png")
        """)
        kinds = [source.kind for item in flow.items
                 for source in item.sources]
        self.assertEqual(kinds, [DATABASE_KIND, "storage", DOCUMENT_KIND])
        self.assertEqual(flow.items[2].kind, PLOT_KIND)

    def test_with_open_handle_is_one_step(self):
        flow = flow_of("""
            import json
            def main():
                with open("out/result.json", "w") as handle:
                    json.dump(rows, handle)
        """)
        self.assertEqual(len(flow.items), 1)
        source = flow.items[0].sources[0]
        self.assertEqual((source.kind, source.label, source.is_output),
                         (DATA_KIND, "result.json", True))
        self.assertEqual([port.name for port in flow.items[0].inputs],
                         ["rows"])

    def test_constants_label_files(self):
        flow = flow_of("""
            import pandas as pd
            INPUT_PATH = "C:/data/input.csv"
            def main():
                table_df = pd.read_csv(INPUT_PATH)
        """)
        self.assertEqual(flow.items[0].sources[0].label, "input.csv")


class ControlFlowTests(unittest.TestCase):
    def test_loops_branches_and_notes(self):
        flow = flow_of("""
            def check(x): ...
            def main():
                for item in items:
                    if check(item):
                        continue
                    else:
                        print(item)
                try:
                    check(1)
                except ValueError:
                    pass
        """)
        loop = flow.items[0]
        self.assertIsInstance(loop, Loop)
        branch = loop.body[0]
        self.assertIsInstance(branch, Branch)
        self.assertEqual(branch.yes_jump, "continue")
        self.assertIn("handler for ValueError", flow.notes[0].message)

    def test_continue_goes_to_loop_end_and_return_to_end(self):
        flow = flow_of("""
            def keep(x): ...
            def main():
                for item in items:
                    if item:
                        continue
                    keep(item)
                if done:
                    return
                keep(2)
        """)
        edges = edges_by_label(layout_flow(flow))
        self.assertIn(("item?", "for item in items", "Yes"), edges)
        self.assertIn(("done?", "END", "Yes"), edges)
        self.assertNotIn(("item?", "keep Keep. in: item: unknown", "Yes"),
                         edges)

    def test_notebook_cells_and_magics(self):
        folder = Path(tempfile.mkdtemp())
        notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {},
                    "cells": [
                        {"cell_type": "markdown", "metadata": {},
                         "source": "# Title"},
                        {"cell_type": "code", "metadata": {},
                         "source": ["%matplotlib inline\n",
                                    "import pandas as pd\n",
                                    "df = pd.read_csv('a.csv')\n"]},
                        {"cell_type": "code", "metadata": {},
                         "source": "%%bash\necho hi\n"}]}
        path = folder / "analysis.ipynb"
        path.write_text(json.dumps(notebook), encoding="utf-8")
        flow = build_flow(load_script(path))
        self.assertEqual(flow.script_name, "analysis.ipynb")
        self.assertEqual(flow.items[0].sources[0].label, "a.csv")


class LayoutTests(unittest.TestCase):
    def long_flow(self, count_int: int):
        calls = "\n".join(f"    step_{index}()" for index in range(count_int))
        defs = "\n".join(f"def step_{index}(): ..."
                         for index in range(count_int))
        return flow_of(f"{defs}\ndef main():\n{calls}\n")

    def test_columns_use_lettered_connectors(self):
        diagram = layout_flow(self.long_flow(25), 10)
        self.assertEqual(diagram.column_count, 3)
        letters = sorted(" ".join(node.label) for node in diagram.nodes
                         if node.kind == CONNECTOR_KIND)
        self.assertEqual(letters, ["A", "A", "B", "B"])
        self.assertEqual(
            [finding for finding in check_diagram(diagram, 10)
             if finding.severity != "info"], [])

    def test_no_shapes_overlap(self):
        flow = build_flow(load_script(EXAMPLES / "station_report.py"))
        diagram = layout_flow(flow, 6)
        boxes = [node for node in diagram.nodes]
        for index, first in enumerate(boxes):
            for second in boxes[index + 1:]:
                overlap = (first.x_px < second.x_px + second.width
                           and second.x_px < first.x_px + first.width
                           and first.y_px < second.y_px + second.height
                           and second.y_px < first.y_px + first.height)
                self.assertFalse(overlap, (first.label, second.label))

    def test_example_meets_all_rules(self):
        flow = build_flow(load_script(EXAMPLES / "station_report.py"))
        diagram = layout_flow(flow)
        findings = check_diagram(diagram)
        self.assertEqual([finding.code for finding in findings
                          if finding.severity == "error"], [])
        kinds = {node.kind for node in diagram.nodes}
        self.assertTrue({LOOP_OPEN_KIND, LOOP_CLOSE_KIND, LEGEND_KIND,
                         PLOT_KIND} <= kinds)


class RenderTests(unittest.TestCase):
    def test_drawio_is_valid_and_deterministic(self):
        flow = build_flow(load_script(EXAMPLES / "station_report.py"))
        first = render_drawio_str(layout_flow(flow))
        second = render_drawio_str(layout_flow(build_flow(
            load_script(EXAMPLES / "station_report.py"))))
        self.assertEqual(first, second)
        root = ET.fromstring(first)
        cells = list(root.iter("mxCell"))
        ids = {cell.get("id") for cell in cells}
        for cell in cells:
            if cell.get("edge"):
                self.assertIn(cell.get("source"), ids)
                self.assertIn(cell.get("target"), ids)
        self.assertIn("&lt;b&gt;flag_heat_events&lt;/b&gt;", first)

    def test_svg_is_valid_and_shows_every_label(self):
        flow = build_flow(load_script(EXAMPLES / "station_report.py"))
        diagram = layout_flow(flow)
        text = render_svg_str(diagram)
        root = ET.fromstring(text)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertEqual(
            len([node for node in root.iter() if node.tag.endswith(
                "polyline")]), len(diagram.edges))
        self.assertIn(">flag_heat_events</text>", text)
        self.assertIn(">hot_hours.png</text>", text)

    def test_rules_find_open_ends_and_unclosed_loops(self):
        flow = build_flow(load_script(EXAMPLES / "station_report.py"))
        diagram = layout_flow(flow)
        titled = next(node for node in diagram.nodes if node.has_title)
        diagram.edges = [edge for edge in diagram.edges
                         if edge.source_id != titled.node_id]
        diagram.nodes = [node for node in diagram.nodes
                         if node.kind != LOOP_CLOSE_KIND]
        codes = {finding.code for finding in check_diagram(diagram)}
        self.assertTrue({"FB003", "FB004"} <= codes)


def write_tree(files_dict: dict[str, str]) -> Path:
    """Write files (relative path -> text) into a new temporary folder."""
    folder = Path(tempfile.mkdtemp())
    for name_str, text_str in files_dict.items():
        path = folder / name_str
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text_str), encoding="utf-8")
    return folder


def edge_names(project) -> set[tuple[str, str]]:
    """Import edges as (importer path, imported path) strings."""
    return {(project.files[source].path.as_posix(),
             project.files[target].path.as_posix())
            for source, target in project.edges}


class MermaidAndPageTests(unittest.TestCase):
    def setUp(self):
        flow = build_flow(load_script(EXAMPLES / "station_report.py"))
        self.diagram = layout_flow(flow, 1_000_000)

    def test_mermaid_flowchart_has_shapes_edges_and_legend(self):
        text = render_mermaid_str(self.diagram)
        self.assertTrue(text.startswith('---\ntitle: "station_report.py"'))
        self.assertIn("flowchart TD", text)
        self.assertIn('(["START"])', text)
        self.assertIn('{"event_count_int == 0?"}', text)
        self.assertIn('[/"heat_summary.csv"/]', text)
        self.assertIn('-->|"Yes"|', text)
        self.assertIn("classDef module1 fill:", text)
        self.assertIn('legend1["station_utils.py"]', text)
        self.assertNotIn("((", text)  # one column: no connectors

    def test_mermaid_escapes_label_text(self):
        node = self.diagram.nodes[-1]
        node.label = ['say "hi" <now> | `x` & y']
        text = render_mermaid_str(self.diagram)
        self.assertIn("say #quot;hi#quot; #lt;now#gt; #124; #96;x#96; "
                      "#amp; y", text)

    def test_html_page_embeds_the_svg(self):
        page = render_html_str(self.diagram, ["line 3: not drawn"])
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("<svg", page)
        self.assertIn("<li>line 3: not drawn</li>", page)


class ProjectTests(unittest.TestCase):
    def test_example_folder(self):
        project = load_project(EXAMPLES)
        kinds = {info.path.name: info.kind for info in project.files}
        self.assertEqual(kinds, {"station_report.py": ENTRY_KIND,
                                 "station_utils.py": MODULE_KIND})
        self.assertEqual(edge_names(project),
                         {("station_report.py", "station_utils.py")})
        utils = next(info for info in project.files
                     if info.path.name == "station_utils.py")
        self.assertEqual(utils.reads, ["*.parquet"])

    def test_package_relative_and_sibling_imports(self):
        folder = write_tree({
            "run.py": """
                from shop import orders
                if __name__ == "__main__":
                    orders.place()
            """,
            "shop/__init__.py": '"""The shop package."""\n',
            "shop/orders.py": """
                from .stock import reserve
                from shop.prices import price_of
                def place(): ...
            """,
            "shop/stock.py": "def reserve(): ...\n",
            "shop/prices.py": "import json\ndef price_of(): ...\n",
            "scripts/report.py": """
                import helpers
                helpers.write_report()
            """,
            "scripts/helpers.py": """
                def write_report():
                    rows_df.to_csv("report.csv")
            """,
            "tests/test_shop.py": "import shop\n",
            ".venv/lib/x.py": "import shop\n",
        })
        project = load_project(folder)
        self.assertEqual(edge_names(project), {
            ("run.py", "shop/orders.py"),
            ("shop/orders.py", "shop/stock.py"),
            ("shop/orders.py", "shop/prices.py"),
            ("scripts/report.py", "scripts/helpers.py")})
        kinds = {info.path.as_posix(): info.kind for info in project.files}
        self.assertEqual(kinds["shop/__init__.py"], PACKAGE_KIND)
        self.assertEqual(kinds["scripts/report.py"], ENTRY_KIND)
        helpers = next(info for info in project.files
                       if info.path.name == "helpers.py")
        self.assertEqual(helpers.writes, ["report.csv"])
        self.assertNotIn("tests/test_shop.py", kinds)
        with_tests = load_project(folder, include_tests=True)
        self.assertIn("tests/test_shop.py", {
            info.path.as_posix() for info in with_tests.files})

    def test_folder_inside_a_package_and_cycles(self):
        folder = write_tree({
            "pkg/__init__.py": "",
            "pkg/a.py": "from pkg.b import g\ndef f(): ...\n",
            "pkg/b.py": "from pkg import a\ndef g(): ...\n",
            "pkg/nb.ipynb": json.dumps({
                "nbformat": 4, "nbformat_minor": 5, "metadata": {},
                "cells": [{"cell_type": "code", "metadata": {},
                           "source": "print(1)\n", "outputs": [],
                           "execution_count": None}]}),
        })
        project = load_project(folder / "pkg")
        self.assertEqual(edge_names(project), {("a.py", "b.py"),
                                               ("b.py", "a.py")})
        kinds = {info.path.name: info.kind for info in project.files}
        self.assertEqual(kinds["nb.ipynb"], NOTEBOOK_KIND)
        diagram = layout_project(project)
        blocks = [node for node in diagram.nodes
                  if node.node_id.startswith("file")]
        self.assertEqual(len(blocks), 4)
        for first in blocks:  # blocks never overlap
            for second in blocks:
                if first is not second:
                    self.assertFalse(
                        first.x_px < second.x_px + second.width
                        and second.x_px < first.x_px + first.width
                        and first.y_px < second.y_px + second.height
                        and second.y_px < first.y_px + first.height)

    def test_unreadable_files_are_noted(self):
        folder = write_tree({"good.py": "x = 1\n", "bad.py": "def (:\n"})
        project = load_project(folder)
        self.assertEqual([info.path.name for info in project.files],
                         ["good.py"])
        self.assertTrue(project.notes[0].startswith("bad.py: not drawn"))

class CommandLineTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(output):
            code = main(list(arguments))
        return code, output.getvalue()

    def test_writes_once_and_refuses_overwrite(self):
        folder = Path(tempfile.mkdtemp())
        target = folder / "out.drawio"
        script = str(EXAMPLES / "station_report.py")
        original = (EXAMPLES / "station_report.py").read_bytes()
        self.assertEqual(self.run_cli(script, "-o", str(target))[0], 0)
        code, text = self.run_cli(script, "-o", str(target))
        self.assertEqual(code, 2)
        self.assertIn("--force", text)
        self.assertEqual(self.run_cli(script, "-o", str(target),
                                      "--force")[0], 0)
        self.assertEqual((EXAMPLES / "station_report.py").read_bytes(),
                         original)

    def test_check_mode_and_syntax_errors(self):
        folder = Path(tempfile.mkdtemp())
        bad = folder / "bad.py"
        bad.write_text("def broken(:\n", encoding="utf-8")
        self.assertEqual(self.run_cli(str(bad))[0], 2)
        code, _ = self.run_cli(str(EXAMPLES / "station_report.py"),
                               "--check")
        self.assertEqual(code, 0)
        self.assertFalse((folder / "bad.drawio").exists())

    def test_overrides_replace_descriptions(self):
        folder = Path(tempfile.mkdtemp())
        overrides = folder / "blueprint.toml"
        overrides.write_text(
            '[blocks.flag_heat_events]\ndescription = "Find hot hours."\n',
            encoding="utf-8")
        target = folder / "out.drawio"
        code, _ = self.run_cli(str(EXAMPLES / "station_report.py"), "-o",
                               str(target), "--overrides", str(overrides))
        self.assertEqual(code, 0)
        self.assertIn("Find hot hours.", target.read_text(encoding="utf-8"))


    def test_folder_mode_and_output_formats(self):
        folder = Path(tempfile.mkdtemp())
        for suffix in (".md", ".mmd", ".html", ".svg", ".drawio"):
            target = folder / f"overview{suffix}"
            code, out = self.run_cli(str(EXAMPLES), "-o", str(target))
            self.assertEqual(code, 0, out)
            self.assertIn("2 files, 1 imports", out)
            self.assertTrue(target.read_text(encoding="utf-8"))
        code, _ = self.run_cli(str(EXAMPLES / "station_report.py"), "-o",
                               str(folder / "flow.md"))
        self.assertEqual(code, 0)
        self.assertIn("```mermaid",
                      (folder / "flow.md").read_text(encoding="utf-8"))
        self.assertEqual(self.run_cli(str(EXAMPLES), "-o",
                                      str(folder / "x.png"))[0], 2)
        self.assertFalse((folder / "x.png").exists())
        self.assertFalse((EXAMPLES / "architecture.drawio").exists())


if __name__ == "__main__":
    unittest.main()
