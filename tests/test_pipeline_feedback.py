"""Exercise all three packages through the integrated drafting command."""

from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from flowblueprint.cli import main


class PipelineFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'analysis.py'
        self.source.write_text(
            'def calculate_value(df):\n'
            '    """Retain the business explanation."""\n'
            '    m=df.copy()\n    return m\n\n'
            'if __name__ == "__main__":\n'
            '    print(calculate_value([1, 2]))\n', 'utf-8')

    def invoke(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = main([str(argument) for argument in arguments])
        return code, output.getvalue()

    def test_three_stages_keep_original_and_draw_final_hashes(self):
        original = self.source.read_bytes()
        bundle = self.root / 'bundle'
        code, text = self.invoke(self.source, '--pipeline-to', bundle)
        self.assertEqual(code, 1, text)  # context/style review remains
        self.assertTrue((bundle / 'review.md').is_file(), text)
        record = json.loads((bundle / 'workflow.json').read_text('utf-8'))
        self.assertEqual(record['modularization'], 'complete')
        self.assertEqual(record['refactoring']['status'], 'findings')
        self.assertTrue(record['refactoring']['context_questions'])
        self.assertFalse(record['behavior_verified'])
        self.assertEqual(self.source.read_bytes(), original)
        for relative, digest in record['generated_source_sha256'].items():
            self.assertEqual(sha256((bundle / 'project' / relative)
                                   .read_bytes()).hexdigest(), digest)
        self.assertEqual(len(ET.parse(bundle / 'architecture.drawio')
                             .getroot().findall('diagram')), 2)
        details = (bundle / 'function_details.drawio').read_text('utf-8')
        self.assertIn('calculate_value', details)
        self.assertIn('Declared body:', details)
        self.assertNotIn('.flowblueprint-',
                         (bundle / 'refactrail.json').read_text('utf-8'))
        for path in (bundle / 'project').rglob('*.py'):
            compile(path.read_bytes(), str(path), 'exec')

    def test_refactoring_error_cannot_be_reported_as_complete(self):
        bundle = self.root / 'bundle'
        with patch('flowblueprint.workflow_review.prepare_refactoring_dict',
                   side_effect=ValueError('deliberate stage failure')):
            code, text = self.invoke(self.source, '--pipeline-to', bundle)
        self.assertEqual(code, 2, text)
        self.assertFalse(bundle.exists())

    def test_mutually_exclusive_destinations_fail_before_writing(self):
        first, second = self.root / 'one', self.root / 'two'
        code, text = self.invoke(self.source, '--pipeline-to', first,
                                 '--modularize-to', second)
        self.assertEqual(code, 2, text)
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())

    def test_input_execution_is_never_used_by_any_stage(self):
        marker = self.root / 'must-not-exist'
        self.source.write_text(
            f'from pathlib import Path\nPath({str(marker)!r}).touch()\n',
            'utf-8')
        code, text = self.invoke(self.source, '--pipeline-to',
                                 self.root / 'bundle')
        self.assertIn(code, (0, 1), text)
        self.assertFalse(marker.exists())
