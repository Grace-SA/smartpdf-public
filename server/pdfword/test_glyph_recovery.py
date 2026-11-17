"""Independent Unicode/ink mapping must be unique, bounded, and non-mutating."""
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import pdfplumber
import pypdfium2 as pdf
from test_worker import fixture
from text_geometry import repair_unmapped_glyphs


class GlyphRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name) / 'glyph.pdf'
        fixture(self.source, content=b'BT /F1 12 Tf 48 700 Td (A) Tj ET')
        self.doc = pdfplumber.open(self.source)
        self.pdf = pdf.PdfDocument(self.source)
        self.page = self.pdf[0]
        # Simulate one extractor missing a mapping while the independent PDF
        # renderer retains the synthetic fixture's known Unicode and ink box.
        self.native = self.doc.pages[0].filter(lambda _: True)
        self.native._objects = dict(self.doc.pages[0].objects)
        self.native._objects['char'] = [dict(c, text='(cid:129)') for c in self.doc.pages[0].chars]

    def tearDown(self):
        self.page.close()
        self.pdf.close()
        self.doc.close()
        self.temp.cleanup()

    def test_unique_unicode_recovers_without_mutating_source_view(self):
        recovered = repair_unmapped_glyphs(self.page, self.native)
        self.assertEqual(recovered.chars[0]['text'], 'A')
        self.assertEqual(self.native.chars[0]['text'], '(cid:129)')
        self.assertEqual(self.doc.pages[0].chars[0]['text'], 'A')

    def test_duplicate_targets_cannot_share_one_renderer_glyph(self):
        self.native._objects['char'] *= 2
        self.assertIs(repair_unmapped_glyphs(self.page, self.native), self.native)

    def test_unknown_or_control_unicode_stays_unmapped(self):
        for code in [0, 129, 0xfffd, 0x110000]:
            with self.subTest(code=code), patch.object(pdf.raw, 'FPDFText_GetUnicode', return_value=code):
                self.assertIs(repair_unmapped_glyphs(self.page, self.native), self.native)

    def test_multiple_independent_glyphs_inside_target_are_ambiguous(self):
        second = Path(self.temp.name) / 'two-glyphs.pdf'
        fixture(second, content=b'BT /F1 12 Tf 48 700 Td (AB) Tj ET')
        with pdf.PdfDocument(second) as document, closing(document[0]) as page:
            self.native._objects['char'][0]['x1'] += 12
            self.assertIs(repair_unmapped_glyphs(page, self.native), self.native)

    def test_unsupported_rotation_crop_and_excess_targets_are_unchanged(self):
        with patch.object(self.page, 'get_rotation', return_value=90):
            self.assertIs(repair_unmapped_glyphs(self.page, self.native), self.native)
        cropped = self.native.crop((20, 20, 600, 780))
        self.assertIs(repair_unmapped_glyphs(self.page, cropped), cropped)
        one = self.native.chars[0]
        for count in [257, 60001]:
            self.native._objects['char'] = [one] * count
            self.assertIs(repair_unmapped_glyphs(self.page, self.native), self.native)


if __name__ == '__main__':
    unittest.main()
