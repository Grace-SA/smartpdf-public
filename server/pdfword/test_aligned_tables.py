"""Headed native registers must not swallow prose or invent missing cells."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from pypdf import PdfReader, PdfWriter

from aligned_tables import headed_registers
from test_worker import fixture
from worker import parse_pdf
from exporter import export_word
from docx import Document
from docx.oxml.ns import qn


def word(text, left, top, width=None):
    return dict(text=text, x0=left, x1=left+(width or len(text)*4),
                top=top, bottom=top+8, chars=[])


def register():
    words = []
    for col, left in enumerate([40, 70, 200, 230, 440, 470]):
        if col % 2 == 0:
            words.extend([word('Code', left-3, 40, 18), word('Type', left-3, 52, 18)])
        else:
            words.append(word('Name', left+5, 46))
    for row in range(5):
        for col, left in enumerate([40, 70, 200, 230, 440, 470]):
            words.append(word(str(100+row) if col % 2 == 0 else 'Alpha', left, 72+12*row))
    return words


class AlignedRegisterTests(unittest.TestCase):
    def test_two_header_levels_preserve_vertical_spans_and_each_value(self):
        words = register();before = copy.deepcopy(words)
        tables = headed_registers(words)
        self.assertEqual(words, before)
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual((table['rows'], table['cols']), (7, 6))
        self.assertEqual(sum(c['rowspan'] == 2 for c in table['cells']), 3)
        self.assertEqual([c['text'] for c in table['cells'] if c['row'] == 6],
                         ['104', 'Alpha', '104', 'Alpha', '104', 'Alpha'])

    def test_single_line_header_is_one_row(self):
        words = [w for w in register() if w['top'] >= 72]
        words += [word('Key' if c % 2 == 0 else 'Name', x, 55)
                  for c, x in enumerate([40, 70, 200, 230, 440, 470])]
        self.assertEqual(headed_registers(words)[0]['rows'], 6)

    def test_parallel_numbered_lists_without_complete_header_are_not_tables(self):
        body = [w for w in register() if w['top'] >= 72]
        for header in [[], [word('List one', 40, 50), word('List two', 200, 50), word('List three', 440, 50)]]:
            self.assertEqual(headed_registers(body + header), [])

    def test_missing_values_and_misaligned_columns_are_not_partial_tables(self):
        for top in [72, 96, 120]:
            words = [w for w in register() if not (w['top'] == top and w['x0'] == 200)]
            self.assertEqual(headed_registers(words), [])
        words = register()
        for w in words:
            if w['top'] >= 72 and w['x0'] == 200:
                shift = (w['top']-72)/3
                w['x0'] += shift;w['x1'] += shift
        self.assertEqual(headed_registers(words), [])

    def test_overlapping_or_ambiguous_header_does_not_guess_spans(self):
        for variant in ['wide', 'third-line', 'off-centre']:
            words = register()
            if variant == 'wide':words[0]['x1'] = 180
            elif variant == 'third-line':words.append(word('extra', 37, 44))
            else:
                for w in words:
                    if w['top'] == 46:w['top'] = 36;w['bottom'] = 44
            self.assertEqual(headed_registers(words), [], variant)

    def test_real_pdf_uses_native_text_without_ocr_or_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);source = root/'register.pdf'
            commands = []
            for w in register():
                commands.append(f"BT /F1 8 Tf {w['x0']} {792-w['top']-8} Td ({w['text']}) Tj ET")
            fixture(source, content='\n'.join(commands).encode())
            ocr = Mock(last_engine='test')
            model = parse_pdf(source, root, ocr=ocr)
            ocr.recognize.assert_not_called()
            tables = [b for b in model['pages'][0]['blocks'] if b['kind'] == 'table']
            self.assertEqual(len(tables), 1)
            self.assertEqual((tables[0]['rows'], tables[0]['cols']), (7, 6))
            self.assertEqual(len(model['pages'][0]['blocks']), 1)

    def test_long_register_document_does_not_invoke_page_ocr(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);source = root/'register.pdf'
            commands = [f"BT /F1 8 Tf {w['x0']} {792-w['top']-8} Td ({w['text']}) Tj ET"
                        for w in register()]
            fixture(source, content='\n'.join(commands).encode())
            reader = PdfReader(source);writer = PdfWriter()
            for _ in range(25):writer.add_page(reader.pages[0])
            long_source = root/'long-register.pdf';writer.write(long_source)
            ocr = Mock(last_engine='test');progress = []
            model = parse_pdf(long_source, root, ocr=ocr, progress=progress.append)
            ocr.recognize.assert_not_called()
            self.assertEqual(len(model['pages']), 25)
            self.assertEqual(progress[-1]['completedPages'], 25)
            for page in model['pages']:
                self.assertEqual(len(page['blocks']), 1)
                self.assertEqual((page['blocks'][0]['rows'], page['blocks'][0]['cols']), (7, 6))
            self.assertFalse(list(root.glob('page-*.png')))

    def test_both_header_rows_repeat_after_word_pagination(self):
        table = headed_registers(register())[0]
        table.update(id='p0-b0', reading_order=0)
        model = dict(schema=2, warnings=[], pages=[dict(index=0, width=612, height=792,
                     rotation=0, blocks=[table])])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);out = root/'headed.docx';export_word(model, out, root)
            rows = Document(out).tables[0].rows
            marked = [i for i, row in enumerate(rows) if row._tr.find('.//'+qn('w:tblHeader')) is not None]
            self.assertEqual(marked, [0, 1])


if __name__ == '__main__':
    unittest.main()
