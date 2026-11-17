"""Synthetic source-page margin ownership and unmapped-font fallback boundaries."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from docx import Document
import pdfplumber
from exporter import export_word
from layout import native_page
from model import Rejected
from worker import parse_pdf
from test_worker import fixture


class MarginGlyphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def page(self, index, margins=False, columns=False):
        def block(kind, text, bounds):
            return dict(kind=kind, text=text, bbox=bounds, source='native', size=10)
        body = [block('paragraph', f'Body page {index}', [40, 100, 250, 130])]
        if columns:
            body = [block('paragraph', (side + ' synthetic paragraph. ') * 14,
                          [left, 100 + line * 130, left + 220, 190 + line * 130])
                    for side, left in [('LEFT', 40), ('RIGHT', 330)] for line in range(3)]
        if margins:
            body = [block('header', f'Header {index}', [40, 20, 300, 35]), *body,
                    block('footer', f'Footer {index}', [40, 760, 300, 780])]
        for j, value in enumerate(body):
            value.update(id=f'p{index}-b{j}', reading_order=j)
        return dict(index=index, width=612, height=792, rotation=0, blocks=body)

    def export(self, pages):
        path = self.root / 'result.docx'
        export_word(dict(schema=2, pages=pages, warnings=[]), path, self.root)
        return path, Document(path)

    def test_missing_margins_do_not_inherit_or_modify_adjacent_pages(self):
        _, doc = self.export([self.page(0, True), self.page(1), self.page(2, True)])
        for edge in ['header', 'footer']:
            values = [[p.text for p in getattr(s, edge).paragraphs] for s in doc.sections]
            self.assertEqual(values, [[edge.title() + ' 0'], [''], [edge.title() + ' 2']])

    def test_column_sections_inherit_the_current_source_page_margins(self):
        _, doc = self.export([self.page(0, True, columns=True)])
        self.assertGreater(len(doc.sections), 1)
        for section in doc.sections:
            self.assertEqual([p.text for p in section.header.paragraphs], ['Header 0'])
            self.assertEqual([p.text for p in section.footer.paragraphs], ['Footer 0'])

    def test_two_hundred_marginless_pages_do_not_create_empty_parts(self):
        path, _ = self.export([self.page(i) for i in range(200)])
        with zipfile.ZipFile(path) as archive:
            self.assertFalse(any(n.startswith(('word/header', 'word/footer')) for n in archive.namelist()))

    def test_unmapped_font_glyph_uses_ocr_and_keeps_the_page_editable(self):
        source = self.root / 'unmapped.pdf'
        fixture(source, content=b'BT /F1 12 Tf 48 700 Td (\x81) Tj ET')
        with pdfplumber.open(source) as doc:
            self.assertEqual(doc.pages[0].chars[0]['text'], '(cid:129)')
            with self.assertRaisesRegex(Rejected, 'Layout needs OCR'):
                native_page(doc.pages[0])
        class Recognizer:
            calls = 0
            def recognize(self, *args, **kwargs):
                self.calls += 1
                return [dict(kind='paragraph', text='Recovered glyph', bbox=[48, 82, 180, 96], source='ocr')]
        ocr = Recognizer()
        model = parse_pdf(source, self.root, ocr=ocr)
        self.assertEqual(ocr.calls, 1)
        self.assertEqual(model['pages'][0]['blocks'][0]['text'], 'Recovered glyph')

    def test_literal_printed_cid_notation_remains_native(self):
        source = self.root / 'literal.pdf'
        fixture(source, content=b'BT /F1 12 Tf 48 700 Td (Literal \\(cid:129\\) text) Tj ET')
        model = parse_pdf(source, self.root)
        self.assertEqual(model['pages'][0]['blocks'][0]['text'], 'Literal (cid:129) text')
        self.assertEqual(model['pages'][0]['blocks'][0]['source'], 'native')


if __name__ == '__main__':
    unittest.main()
