"""Check query-file diagram evidence and editable PNG metadata."""

import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zlib

from flowblueprint.cli import main
from flowblueprint.flow import build_flow
from flowblueprint.model import Step
from flowblueprint.png_metadata import (
    PNG_SIGNATURE_BYTES, add_drawio_to_png_bytes, make_png_chunk_bytes,
)
from flowblueprint.project import collect_sources_tuple
from flowblueprint.source import load_script
from flowblueprint.sql_sources import find_sql_source


def fixture_png():
    return (PNG_SIGNATURE_BYTES
            + make_png_chunk_bytes(b'IHDR', struct.pack('>IIBBBBB',
                                                       1, 1, 8, 2, 0, 0, 0))
            + make_png_chunk_bytes(b'IDAT', zlib.compress(b'\0\xff\xff\xff'))
            + make_png_chunk_bytes(b'IEND', b''))


def chunks(data):
    offset = 8
    result = []
    while offset < len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset+4:offset+8]
        payload = data[offset+8:offset+8+length]
        checksum = struct.unpack_from('>I', data, offset+8+length)[0]
        assert checksum == zlib.crc32(kind+payload)
        result.append((kind, payload))
        offset += length+12
    return result


def editor_xml(data):
    """Match draw.io: stop at first diagram metadata or first IDAT."""
    for kind, payload in chunks(data):
        if kind == b'IDAT':
            return None
        if kind == b'tEXt':
            keyword, _, value = payload.partition(b'\0')
            if keyword in (b'mxfile', b'mxGraphModel'):
                return unquote(value.decode('ascii'))
    return None


class ReferenceStyleTests(unittest.TestCase):
    def test_query_loader_argument_and_keyword_forms(self):
        for expression, label in (
            ('utility.get_sql_query(context, "report.sql")', 'report.sql'),
            ('load_sql(filename="sql/report.sql")', 'sql/report.sql'),
            ('_funcloom_load_sql_str("report_query_4.sql")',
             'sql/report_query_4.sql'),
            ('Path("sql/report.sql").read_text(encoding="utf-8")',
             'sql/report.sql'),
        ):
            source = find_sql_source(ast.parse(expression).body[0].value)
            self.assertEqual(source.label, label)
            self.assertFalse(source.is_output)

    def test_ambiguous_and_non_loader_calls_are_not_invented(self):
        for expression in ('print("report.sql")', 'load_sql(path)',
                           'get_sql_query("a.sql", "b.sql")',
                           'load_sql(f"{name}.sql")'):
            self.assertIsNone(find_sql_source(
                ast.parse(expression).body[0].value))

    def test_query_shape_is_retained_for_developed_loader(self):
        source = ('def get_sql_query(context, filename):\n'
                  '    """Load the query text."""\n'
                  '    raise RuntimeError("must not execute")\n'
                  'query = get_sql_query(context, "report.sql")\n'
                  'rows = database.read_sql(sql=query, con=connection)\n')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'main.py'
            path.write_text(source, encoding='utf-8')
            flow = build_flow(load_script(path))
            labels = [item.label for step in flow.items if isinstance(step, Step)
                      for item in step.sources]
            self.assertIn('report.sql', labels)
            reads, _ = collect_sources_tuple(path, ast.parse(source))
            self.assertIn('report.sql', reads)

    def test_nested_loader_does_not_hide_sql_execution(self):
        source = ('def load_sql(filename):\n'
                  '    return "SELECT 1"\n'
                  'connection.execute(load_sql("report.sql"))\n')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'main.py'
            path.write_text(source, encoding='utf-8')
            flow = build_flow(load_script(path))
            steps = [step for step in flow.items if isinstance(step, Step)]
            self.assertIn('Execute SQL', steps[0].description)
            labels = [item.label for item in steps[0].sources]
            self.assertIn('report.sql', labels)
            self.assertIn('connection (SQL connection)', labels)

    def test_editable_xml_roundtrip_and_pixels_unchanged(self):
        xml = '<mxfile><diagram name="\u65e5 &amp; SQL"/></mxfile>'
        original = fixture_png()
        changed = add_drawio_to_png_bytes(original, xml)
        original_chunks = chunks(original)
        changed_chunks = chunks(changed)
        self.assertEqual([pair for pair in changed_chunks if pair[0] != b'tEXt'],
                         original_chunks)
        metadata = [value for kind, value in changed_chunks if kind == b'tEXt']
        self.assertEqual(len(metadata), 1)
        self.assertEqual(unquote(metadata[0].partition(b'\0')[2].decode()), xml)
        ET.fromstring(unquote(metadata[0].partition(b'\0')[2].decode()))
        self.assertEqual(editor_xml(changed), xml)
        self.assertEqual(add_drawio_to_png_bytes(changed, xml), changed)

    def test_malformed_png_is_refused(self):
        original = fixture_png()
        for data in (b'not a PNG', original[:-1], original+b'junk',
                     original[:20] + b'bad' + original[23:]):
            with self.assertRaises(ValueError):
                add_drawio_to_png_bytes(data, '<mxfile/>')

    def test_drawio_png_cli_embeds_actual_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'main.py'
            source.write_text('query = utility.get_sql_query({}, "report.sql")\n'
                              'print(query)\n', encoding='utf-8')
            output = root/'architecture.drawio.png'
            with patch('flowblueprint.cli.render_png_bytes',
                       return_value=fixture_png()), redirect_stdout(io.StringIO()):
                status = main([str(source), '-o', str(output)])
                self.assertEqual(status, 0)
                self.assertEqual(main([str(source), '-o', str(output),
                                       '--up-to-date']), 0)
            xml = editor_xml(output.read_bytes())
            self.assertIsNotNone(xml)
            self.assertIn('report.sql', xml)
            self.assertGreater(len(ET.fromstring(xml).findall('diagram')), 0)

    def test_plain_png_does_not_add_drawio_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'main.py'
            source.write_text('print(1)\n')
            output = root/'image.png'
            with patch('flowblueprint.cli.render_png_bytes',
                       return_value=fixture_png()), redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(source), '-o', str(output)]), 0)
            self.assertEqual(output.read_bytes(), fixture_png())
