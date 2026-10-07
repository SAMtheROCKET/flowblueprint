"""Regressions for loops, function pages and multi-page output."""

import contextlib
import io
from pathlib import Path
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET

from flowblueprint.cli import main
from flowblueprint.document import list_page_flows_list
from flowblueprint.flow import build_flow
from flowblueprint.layout import layout_flow
from flowblueprint.model import (
    LOOP_CLOSE_KIND, LOOP_FRAME_KIND, LOOP_OPEN_KIND, TERMINATOR_KIND, Branch)
from flowblueprint.rules import check_diagram
from flowblueprint.source import load_script
from flowblueprint.svg import render_svg_str

SCRIPT = '''
import csv

def load_rows(path):
    rows = []
    with open(path) as handle:
        for row in csv.DictReader(handle):
            if not row["amount"]:
                continue
            rows.append(row)
    return rows

def main():
    rows = load_rows("sales.csv")
    for row in rows:
        print("row", row)

if __name__ == "__main__":
    main()
'''


class PagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.script = self.folder / "sales.py"
        self.script.write_text(textwrap.dedent(SCRIPT), encoding="utf-8")
        self.flow = build_flow(load_script(self.script))

    def test_loops_have_a_back_arrow_and_a_frame(self):
        diagram = layout_flow(self.flow)
        kinds = {node.node_id: node.kind for node in diagram.nodes}
        back_edges = [edge for edge in diagram.edges if edge.back_depth]
        self.assertEqual(len(back_edges), 1)
        self.assertEqual(kinds[back_edges[0].source_id], LOOP_CLOSE_KIND)
        self.assertEqual(kinds[back_edges[0].target_id], LOOP_OPEN_KIND)
        self.assertEqual(back_edges[0].label, "repeat")
        self.assertIn(LOOP_FRAME_KIND, kinds.values())
        labels = [" ".join(node.label) for node in diagram.nodes]
        self.assertIn("For each row in rows", labels)
        self.assertIn("Next row", labels)

    def test_a_loop_is_never_split_across_columns(self):
        diagram = layout_flow(self.flow, 3)
        columns = {node.column for node in diagram.nodes
                   if node.kind in (LOOP_OPEN_KIND, LOOP_CLOSE_KIND)}
        self.assertEqual(len(columns), 1)

    def test_called_functions_get_their_own_page(self):
        self.assertEqual([page.start_label for page in self.flow.functions],
                         ["load_rows(path)"])
        page = self.flow.functions[0]
        self.assertEqual(page.end_label, "Return rows")
        diagram = layout_flow(page)
        self.assertEqual([finding for finding in check_diagram(diagram)
                          if finding.severity == "error"], [])
        terminators = [" ".join(node.label) for node in diagram.nodes
                       if node.kind == TERMINATOR_KIND]
        self.assertEqual(terminators, ["load_rows(path)", "Return rows"])

    def test_function_blocks_describe_their_body_and_type(self):
        step = self.flow.items[0]
        self.assertEqual(step.title, "load_rows")
        self.assertIn("opens path", step.description)
        self.assertIn("reads CSV rows", step.description)
        self.assertEqual(step.outputs[0].dtype, "list")

    def test_print_shows_its_message(self):
        loop = self.flow.items[1]
        self.assertEqual(loop.body[0].description, "Print 'row', row.")

    def test_levels_choose_the_pages(self):
        full = list_page_flows_list(self.flow, "full", 4)
        self.assertEqual(len(full), 2)  # short main flow: no overview
        summary = list_page_flows_list(self.flow, "summary", 4)
        self.assertEqual(len(summary), 1)

    def test_drawio_has_one_tab_per_page_and_svg_has_fonts(self):
        output = self.folder / "sales.drawio"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.script), "-o", str(output)]), 0)
        pages = ET.parse(output).getroot().findall("diagram")
        self.assertEqual([page.get("name") for page in pages],
                         ["sales.py", "sales.py: load_rows(path)"])
        svg_str = render_svg_str(layout_flow(self.flow))
        self.assertIn("'DejaVu Sans'", svg_str)

    def test_try_handlers_are_decisions(self):
        path = self.folder / "risky.py"
        path.write_text(textwrap.dedent('''
            def main():
                try:
                    run()
                except KeyError:
                    print("missing")
                    return
        '''), encoding="utf-8")
        flow = build_flow(load_script(path))
        handler = flow.items[-1]
        self.assertIsInstance(handler, Branch)
        self.assertEqual(handler.condition, "KeyError raised?")
        self.assertEqual(handler.yes_jump, "return")

    def test_project_folder_adds_entry_point_pages(self):
        package = self.folder / "proj"
        package.mkdir()
        (package / "run.py").write_text(textwrap.dedent(SCRIPT),
                                        encoding="utf-8")
        output = self.folder / "proj.md"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(package), "-o", str(output)]), 0)
        headings = [line for line in output.read_text(
            encoding="utf-8").splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["## proj architecture", "## run.py",
                                    "## run.py: load_rows(path)"])


if __name__ == "__main__":
    unittest.main()
