"""Guard the editable PNG reader boundary and preserve unrelated chunks."""

import unittest
from urllib.parse import quote
import zlib

from flowblueprint.png_metadata import (
    PNG_SIGNATURE_BYTES, add_drawio_to_png_bytes, make_png_chunk_bytes,
)
from test_sql_reference import chunks, editor_xml, fixture_png


class PngMetadataTests(unittest.TestCase):
    def test_repairs_late_metadata_with_multiple_image_chunks(self):
        header, image, end = chunks(fixture_png())
        split = len(image[1]) // 2
        old = b'mxfile\0' + quote('<mxfile/>', safe='').encode('ascii')
        original = PNG_SIGNATURE_BYTES + b''.join(
            make_png_chunk_bytes(kind, payload) for kind, payload in (
                header, (b'IDAT', image[1][:split]),
                (b'IDAT', image[1][split:]), (b'tEXt', old), end))
        self.assertIsNone(editor_xml(original))
        xml = '<mxfile><diagram name="\u65e5\u672c\u8a9e &amp; %20 +"/></mxfile>'
        fixed = add_drawio_to_png_bytes(original, xml)
        self.assertEqual(editor_xml(fixed), xml)
        self.assertEqual(
            [pair for pair in chunks(fixed) if pair[0] != b'tEXt'],
            [pair for pair in chunks(original) if pair[0] != b'tEXt'])
        self.assertEqual(add_drawio_to_png_bytes(fixed, xml), fixed)

    def test_removes_old_diagram_keywords_before_and_after_image(self):
        original = fixture_png()
        for kind in (b'tEXt', b'zTXt', b'iTXt'):
            for keyword in (b'mxfile', b'mxGraphModel'):
                with self.subTest(kind=kind, keyword=keyword):
                    old = make_png_chunk_bytes(kind, keyword + b'\0stale')
                    data = original[:33] + old + original[33:-12]
                    data += old + original[-12:]
                    fixed = add_drawio_to_png_bytes(data, '<mxfile/>')
                    self.assertEqual(editor_xml(fixed), '<mxfile/>')
                    metadata = [pair for pair in chunks(fixed)
                                if pair[0] in (b'tEXt', b'zTXt', b'iTXt')]
                    self.assertEqual(len(metadata), 1)
                    self.assertEqual(metadata[0][0], b'tEXt')
                    self.assertTrue(metadata[0][1].startswith(b'mxfile\0'))

    def test_preserves_other_metadata_bytes(self):
        original = fixture_png()
        before = make_png_chunk_bytes(b'tEXt', b'Author\0Example')
        after = make_png_chunk_bytes(b'zTXt', b'Comment\0\0'
                                     + zlib.compress(b'Unrelated text'))
        data = original[:33] + before + original[33:-12] + after
        data += original[-12:]
        fixed = add_drawio_to_png_bytes(data, '<mxfile/>')
        self.assertIn(before, fixed)
        self.assertIn(after, fixed)
        self.assertEqual(editor_xml(fixed), '<mxfile/>')
        self.assertEqual(
            [pair for pair in chunks(fixed)
             if not pair[1].startswith(b'mxfile\0')], chunks(data))

    def test_missing_image_data_is_refused(self):
        original = fixture_png()
        data = original[:33] + original[-12:]
        with self.assertRaisesRegex(ValueError, 'IDAT'):
            add_drawio_to_png_bytes(data, '<mxfile/>')

    def test_missing_or_malformed_header_is_refused(self):
        original = fixture_png()
        for data in (original[:8] + original[33:],
                     original[:8] + make_png_chunk_bytes(b'IHDR', b'bad')
                     + original[33:]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                add_drawio_to_png_bytes(data, '<mxfile/>')

    def test_checksums_after_insertion_point_are_still_checked(self):
        original = fixture_png()
        bad = make_png_chunk_bytes(b'tEXt', b'Comment\0truncated checksum')
        bad = bad[:-1] + bytes([bad[-1] ^ 1])
        broken_image = bytearray(original)
        broken_image[41] ^= 1
        for data in (bytes(broken_image),
                     original[:-12] + bad + original[-12:]):
            with self.subTest(data=data):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    add_drawio_to_png_bytes(data, '<mxfile/>')


if __name__ == '__main__':
    unittest.main()
