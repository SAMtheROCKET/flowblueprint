"""Regression evidence for reference canvases and new-copy workflows."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from flowblueprint.cli import main
from flowblueprint.document import stack_pages_diagram
from flowblueprint.model import (
    Branch, Flow, Loop, Port, Source, Step, CONNECTOR_KIND, DATA_KIND,
    DATABASE_KIND, PROCESS_KIND, TEXT_KIND,
)
from flowblueprint.png import PngUnavailableError
from flowblueprint.reference import read_reference_flows_tuple
from flowblueprint.reference_layout import (
    layout_reference_canvas, build_reference_pages_list,
)
from flowblueprint.rules import check_diagram
from flowblueprint.svg import render_svg_str
from flowblueprint.workflow import prepare_workflow_dict


class ReferenceCanvasTests(unittest.TestCase):
    def sample_flow(self, title='report.py'):
        return Flow(title, [
            Step(PROCESS_KIND, 'load_rows', 'Load records.',
                 [Port('filename_str', 'str')], [Port('rows_list', 'list')],
                 'loader.py', sources=[Source(DATA_KIND, 'records.csv')]),
            Loop('For each row in rows_list', [
                Step(PROCESS_KIND, f'process_{index}', 'Process row.')
                for index in range(8)
            ] + [Branch('row.amount > 0', [Step(
                PROCESS_KIND, 'store_row', sources=[Source(
                    DATABASE_KIND, 'results_db', True)])])]),
        ], ['loader.py'])

    def test_canvases_keep_operational_shapes_and_io(self):
        flows = [self.sample_flow(), self.sample_flow('other.py')]
        before = deepcopy(flows)
        pages = build_reference_pages_list(flows, 'Example', max_blocks_int=4)
        self.assertEqual(len(pages), 2)
        self.assertEqual(flows, before)
        detailed = pages[-1]
        kinds = {node.kind for node in detailed.nodes}
        self.assertTrue({'terminator', 'process', 'decision', 'loop_open',
                         'loop_close', 'legend', DATA_KIND, DATABASE_KIND,
                         CONNECTOR_KIND} <= kinds)
        labels = '\n'.join(' '.join(node.label) for node in detailed.nodes)
        self.assertIn('in: filename_str: str', labels)
        self.assertIn('out: rows_list: list', labels)
        self.assertEqual(len({node.node_id for node in detailed.nodes}),
                         len(detailed.nodes))
        self.assertFalse([item for item in check_diagram(detailed, 4)
                          if item.severity == 'error'])
        for edge in detailed.edges:
            if edge.source_id.startswith('f1_'):
                self.assertTrue(edge.target_id.startswith('f1_'))

    def test_continuing_loops_keep_pairs_routes_and_unique_connectors(self):
        canvas = layout_reference_canvas(
            [self.sample_flow(), self.sample_flow('other.py')], 'project', 3)
        nodes = {node.node_id: node for node in canvas.nodes}
        repeated = [edge for edge in canvas.edges if edge.back_depth]
        self.assertEqual(len(repeated), 2)
        for edge in repeated:
            self.assertNotEqual(nodes[edge.source_id].column,
                                nodes[edge.target_id].column)
            self.assertTrue(edge.waypoints)
            self.assertGreater(max(y for _, y in edge.waypoints),
                               max(n.y_px + n.height for n in nodes.values()
                                   if n.kind != TEXT_KIND))
        counts = {}
        for node in nodes.values():
            if node.kind == CONNECTOR_KIND:
                key = tuple(node.label)
                counts[key] = counts.get(key, 0) + 1
        self.assertTrue(counts)
        self.assertEqual(set(counts.values()), {2})
        self.assertGreaterEqual(min(x for edge in canvas.edges
                                    for x, _ in edge.waypoints), 0)
        ET.fromstring(render_svg_str(canvas))

    def test_stacking_reserves_repeat_arrow_space(self):
        first = layout_reference_canvas([self.sample_flow()], 'first', 3)
        second = layout_reference_canvas([self.sample_flow()], 'second', 3)
        stacked = stack_pages_diagram([first, second])
        first_bottom = max(y for edge in stacked.edges
                           if edge.source_id.startswith('p1')
                           for _, y in edge.waypoints)
        second_top = min(node.y_px for node in stacked.nodes
                         if node.node_id.startswith('p2'))
        self.assertGreater(second_top, first_bottom)

    def test_shared_modules_keep_the_same_colour_across_scripts(self):
        first = self.sample_flow()
        second = self.sample_flow('second.py')
        second.modules.insert(0, 'another.py')
        canvas = layout_reference_canvas([first, second], 'project')
        colours = {node.fill for node in canvas.nodes
                   if node.label and node.label[0] == 'load_rows'}
        self.assertEqual(len(colours), 1)


class ReferenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.script = self.root / 'invoice.py'
        self.script.write_text(
            'base_amount = 120\ntax_rate = 0.1\n'
            'tax_amount = base_amount * tax_rate\n'
            'total_amount = base_amount + tax_amount\n'
            'print(total_amount)\n', 'utf-8')

    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = main([str(argument) for argument in args])
        return code, output.getvalue()

    def test_modularize_diagrams_generated_copy_and_preserves_source(self):
        original = self.script.read_bytes()
        bundle = self.root / 'bundle'
        code, text = self.invoke(self.script, '--modularize-to', bundle)
        self.assertEqual(code, 0, text)
        self.assertEqual(original, self.script.read_bytes())
        record = json.loads((bundle / 'workflow.json').read_text('utf-8'))
        self.assertEqual(record['modularization'], 'complete')
        self.assertFalse(record['source_execution'])
        self.assertFalse(record['behavior_verified'])
        self.assertTrue(record['review_required'])
        self.assertEqual(record['diagram_source'], 'project')
        self.assertTrue((bundle / 'project/src/pipeline.py').is_file())
        self.assertEqual(len(ET.parse(bundle / 'architecture.drawio')
                             .getroot().findall('diagram')), 2)
        labels = (bundle / 'detailed.drawio').read_text('utf-8')
        self.assertIn('steps.py', labels)
        for step in record['modularization_report']['steps']:
            self.assertIn(step['name'], labels)
        self.assertNotIn('.flowblueprint-',
                         (bundle / 'workflow.json').read_text('utf-8'))
        for path, digest in record['generated_source_sha256'].items():
            self.assertEqual(sha256((bundle / 'project' / path)
                                   .read_bytes()).hexdigest(), digest)

    def test_notebook_workflow_retains_original_bytes(self):
        notebook = self.root / 'invoice.ipynb'
        notebook.write_text(json.dumps({
            'nbformat': 4, 'nbformat_minor': 5, 'metadata': {}, 'cells': [{
                'cell_type': 'code', 'metadata': {}, 'outputs': [],
                'execution_count': None,
                'source': self.script.read_text('utf-8'), 'id': 'invoice',
            }]}), 'utf-8')
        original = notebook.read_bytes()
        code, text = self.invoke(notebook, '--modularize-to',
                                 self.root / 'notebook-bundle')
        self.assertEqual(code, 0, text)
        self.assertEqual(notebook.read_bytes(), original)

    def test_existing_bundle_is_never_overwritten_even_with_force(self):
        bundle = self.root / 'existing'
        bundle.mkdir()
        marker = bundle / 'keep.txt'
        marker.write_text('keep', 'utf-8')
        for extra in ([], ['--force']):
            code, _ = self.invoke(self.script, '--modularize-to', bundle,
                                  *extra)
            self.assertEqual(code, 2)
        self.assertEqual(marker.read_text('utf-8'), 'keep')

    def test_output_inside_project_is_refused_before_writes(self):
        project = self.root / 'project'
        project.mkdir()
        (project / 'main.py').write_bytes(self.script.read_bytes())
        code, text = self.invoke(project, '--modularize-to', project / 'out')
        self.assertEqual(code, 2, text)
        self.assertFalse((project / 'out').exists())

    def test_refusal_leaves_no_bundle_or_staging_directory(self):
        self.script.write_text('exec("print(123)")\n', 'utf-8')
        code, text = self.invoke(self.script, '--modularize-to',
                                 self.root / 'refused')
        self.assertEqual(code, 1, text)
        self.assertIn('MOD', text)
        self.assertFalse((self.root / 'refused').exists())
        self.assertFalse(list(self.root.glob('.flowblueprint-*')))

    def test_renderer_failure_does_not_leave_a_completed_bundle(self):
        with patch('flowblueprint.workflow.render_png_bytes',
                   side_effect=PngUnavailableError('renderer missing')):
            code, text = self.invoke(self.script, '--modularize-to',
                                     self.root / 'failed', '--png')
        self.assertEqual(code, 2, text)
        self.assertFalse((self.root / 'failed').exists())
        self.assertFalse(list(self.root.glob('.flowblueprint-*')))

    def test_partial_project_is_explicit_and_returns_one(self):
        project = self.root / 'partial'
        project.mkdir()
        (project / 'good.py').write_bytes(self.script.read_bytes())
        (project / 'bad.py').write_text('exec("print(123)")\n', 'utf-8')
        bundle = self.root / 'partial-bundle'
        code, text = self.invoke(project, '--entry', 'good.py', '--entry',
                                 'bad.py', '--modularize-to', bundle)
        self.assertEqual(code, 1, text)
        record = json.loads((bundle / 'workflow.json').read_text('utf-8'))
        self.assertEqual(record['modularization'], 'partial')
        self.assertEqual((bundle / 'project/bad.py').read_bytes(),
                         (project / 'bad.py').read_bytes())
        self.assertIn('bad.py', record['modularization_report']['kept_scripts'])

    def test_all_refused_project_reports_copied_only(self):
        project = self.root / 'refused-project'
        project.mkdir()
        (project / 'bad.py').write_text('exec("print(123)")\n', 'utf-8')
        bundle = self.root / 'copied-bundle'
        code, text = self.invoke(project, '--entry', 'bad.py',
                                 '--modularize-to', bundle)
        self.assertEqual(code, 1, text)
        record = json.loads((bundle / 'workflow.json').read_text('utf-8'))
        self.assertEqual(record['modularization'], 'copied_only')

    def test_no_target_import_or_execution_in_drawing_or_drafting(self):
        marker = self.root / 'SHOULD_NOT_EXIST'
        self.script.write_text(
            'from pathlib import Path\n'
            f'Path({str(marker)!r}).write_text("executed")\n', 'utf-8')
        for args in (['--view', 'reference', '-o', self.root / 'safe.drawio'],
                     ['--modularize-to', self.root / 'safe-bundle']):
            code, text = self.invoke(self.script, *args)
            self.assertEqual(code, 0, text)
            self.assertFalse(marker.exists())

    def test_reference_levels_and_up_to_date_are_repeatable(self):
        output = self.root / 'repeat.drawio'
        args = [self.script, '--view', 'reference', '-o', output]
        self.assertEqual(self.invoke(*args)[0], 0)
        self.assertEqual(self.invoke(*args, '--up-to-date')[0], 0)
        self.assertEqual(self.invoke(*args)[0], 2)
        for level in ('summary', 'detailed'):
            target = self.root / f'{level}.drawio'
            code, text = self.invoke(self.script, '--view', 'reference',
                                     '--level', level, '-o', target)
            self.assertEqual(code, 0, text)
            self.assertEqual(len(ET.parse(target).getroot()
                                 .findall('diagram')), 1)

    def test_entry_escape_and_compile_failure_are_not_success(self):
        project = self.root / 'small'
        project.mkdir()
        (project / 'module.py').write_text('value = 1\n', 'utf-8')
        for name in ('../invoice.py', str(self.script)):
            code, _ = self.invoke(project, '--view', 'reference',
                                  '--entry', name, '--check')
            self.assertEqual(code, 2)
        self.script.write_text('return 1\n', 'utf-8')
        code, _ = self.invoke(self.script, '--view', 'reference', '--check')
        self.assertEqual(code, 2)

    def test_local_handover_exposes_declared_body_and_retains_call(self):
        (self.root / 'operations.py').write_text(
            'def operate():\n    print("first")\n'
            '    print("second")\n    print("third")\n', 'utf-8')
        self.script.write_text(
            'from operations import operate\n'
            'if __name__ == "__main__":\n    operate()\n', 'utf-8')
        flows, notes = read_reference_flows_tuple(self.script)
        self.assertEqual(flows[0].items[0].title, 'operate')
        self.assertGreater(len(flows[0].items), 1)
        self.assertIn('dispatch', ' '.join(notes))

    def test_sql_assets_and_report_match_generated_project(self):
        self.script.write_text(
            'query_str = "SELECT amount FROM records"\n'
            'print(query_str)\n', 'utf-8')
        bundle = self.root / 'sql-bundle'
        record = prepare_workflow_dict(self.script, bundle,
                                       externalize_sql_bool=True)
        paths = list((bundle / 'project').rglob('*.sql'))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].read_text('utf-8'),
                         'SELECT amount FROM records')
        self.assertTrue(record['modularization_report']['sql_assets'])

    def test_override_wording_applies_to_reference_canvas(self):
        overrides = self.root / 'words.toml'
        overrides.write_text('[blocks."line:1"]\n'
                             'description = "Customer-approved context"\n',
                             'utf-8')
        output = self.root / 'wording.drawio'
        code, text = self.invoke(self.script, '--view', 'reference',
                                 '--overrides', overrides, '-o', output)
        self.assertEqual(code, 0, text)
        self.assertIn('Customer-approved', output.read_text('utf-8'))


class GeneratedBodyTests(unittest.TestCase):
    def test_function_return_does_not_inherit_its_misleading_name_suffix(self):
        from flowblueprint.dtypes import infer_return_dtype_str
        source = ('def factory():\n    def values_list():\n'
                  '        return 4\n    return values_list\n')
        body = ast.parse(source).body[0].body
        self.assertEqual(infer_return_dtype_str(body), 'Callable')
        body[0].decorator_list = [ast.Name('change_value')]
        self.assertNotEqual(infer_return_dtype_str(body), 'Callable')

    def test_package_imports_resolve_without_importing_target_code(self):
        from flowblueprint.source import find_module_file, load_script
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / 'src'
            nested = package / 'nested'
            nested.mkdir(parents=True)
            for directory in (package, nested):
                (directory / '__init__.py').write_text('', 'utf-8')
            helper = package / 'helpers.py'
            helper.write_text('raise RuntimeError("must not import")\n'
                              'def collect():\n    return []\n', 'utf-8')
            entry = package / 'report.py'
            entry.write_text('from src.helpers import collect\n'
                             'rows = collect()\n', 'utf-8')
            info = load_script(entry)
            self.assertEqual(info.developed['collect'].source_path, helper)
            self.assertEqual(find_module_file(nested, '..helpers'), helper)
            self.assertIsNone(find_module_file(nested, '.helpers'))

    def test_context_titles_do_not_disable_generated_step_expansion(self):
        from funcloom import modularize_report, RefineOptions
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'sample.py'
            source.write_text('for value_int in [1, 2]:\n'
                              '    print(value_int)\n', 'utf-8')
            report = modularize_report(source_path=source,
                package_name='src', options_info=RefineOptions(document=True))
            context = root / 'context.toml'
            context.write_text(f'[blocks.{report.steps[0].name}]\n'
                               'title = "Process customer values"\n', 'utf-8')
            bundle = root / 'bundle'
            prepare_workflow_dict(source, bundle, overrides_path=context)
            text = (bundle / 'detailed.drawio').read_text('utf-8')
            self.assertIn('Process customer values', text)
            self.assertIn('shape=loopLimit', text)

    def test_workflow_png_contains_the_same_implementation_page(self):
        from test_sql_reference import fixture_png, editor_xml
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'sample.py'
            source.write_text('print(123)\n', 'utf-8')
            bundle = root / 'bundle'
            with patch('flowblueprint.workflow.render_png_bytes',
                       return_value=fixture_png()):
                prepare_workflow_dict(source, bundle, png_bool=True)
            xml = editor_xml(
                (bundle / 'architecture.drawio.png').read_bytes())
            self.assertIsNotNone(xml)
            self.assertEqual(xml, (bundle / 'detailed.drawio')
                             .read_text('utf-8'))

    def test_detailed_workflow_exposes_loops_decisions_and_sql(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'pipeline.py'
            source.write_text(
                'query_str = "SELECT amount FROM records"\n'
                'for amount_int in [1, 2, 3]:\n'
                '    if amount_int > 1:\n'
                '        print(query_str, amount_int)\n', 'utf-8')
            bundle = root / 'bundle'
            record = prepare_workflow_dict(source, bundle,
                                           externalize_sql_bool=True)
            text = (bundle / 'detailed.drawio').read_text('utf-8')
            self.assertIn('shape=loopLimit', text)
            self.assertIn('rhombus', text)
            self.assertIn('.sql', text)
            self.assertTrue(record['generated_source_sha256'])


if __name__ == '__main__':
    unittest.main()
