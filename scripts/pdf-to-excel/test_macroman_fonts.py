"""Explicit PDF MacRoman mappings, not document-word substitutions."""
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject as D, NameObject as N, NumberObject as I, ArrayObject as A, DecodedStreamObject
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server/pdf-to-excel'))
from source_fonts import repair


def font():
    return D({N('/Type'): N('/Font'), N('/Subtype'): N('/TrueType'),
              N('/BaseFont'): N('/ArialMT'), N('/Encoding'): N('/MacRomanEncoding'),
              N('/FirstChar'): I(32), N('/LastChar'): I(255),
              N('/Widths'): A([I(600)] * 224),
              N('/FontDescriptor'): D({N('/Type'): N('/FontDescriptor'),
                  N('/FontName'): N('/ArialMT'), N('/Flags'): I(32),
                  N('/FontBBox'): A([I(0), I(-200), I(1000), I(900)]),
                  N('/ItalicAngle'): I(0), N('/Ascent'): I(900),
                  N('/Descent'): I(-200), N('/CapHeight'): I(700), N('/StemV'): I(80)})})


class MacRomanGuardTests(unittest.TestCase):
    def test_unembedded_macroman_does_not_change_model_render_input(self):
        # A local proposed standard ToUnicode completion changed PDFium pixels
        # for this accepted font. Until rendering-safe completion is proven,
        # preserve the existing conservative extraction-metadata boundary.
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.pdf', Path(tmp)/'prepared.pdf'
            writer = PdfWriter(); page = writer.add_blank_page(width=300, height=200)
            page[N('/Resources')] = D({N('/Font'): D({N('/F1'): font()})})
            content = DecodedStreamObject()
            content.set_data(b'BT /F1 20 Tf 30 120 Td (A\\336 B\\337 \\200 7.25) Tj ET')
            page[N('/Contents')] = content
            writer.write(source); original = source.read_bytes()
            self.assertEqual(repair(source, output), [])
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), original)
            self.assertNotIn('/ToUnicode', PdfReader(source).pages[0]['/Resources']['/Font']['/F1'])


if __name__ == '__main__':
    unittest.main()
