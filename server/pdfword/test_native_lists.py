"""Original synthetic list regressions; public source PDFs stay outside the repo."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from docx import Document
from worker import convert
from layout import native_page
from model import Rejected
from test_worker import fixture
import pdfplumber


def text(x, y, value):
    escaped = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    return f'BT /F1 12 Tf {x} {y} Td ({escaped}) Tj ET '.encode()


class NativeListTests(unittest.TestCase):
    def test_two_column_ordered_lists_remain_editable_without_ocr(self):
        for punctuation in ('.', ')'):
            with self.subTest(punctuation=punctuation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, output = root / 'source.pdf', root / 'result.docx'
                content = b''
                for index, y in enumerate((720, 680, 640), 1):
                    content += text(48, y, f'Left paragraph {chr(64+index)}')
                    content += text(342, y, f'{index}{punctuation}')
                    content += text(362, y, f'Ordered entry {chr(64+index)}')
                    content += text(362, y - 14, 'Continued editable prose')
                fixture(source, content=content)
                original = source.read_bytes()
                with patch('worker.OCR.recognize', side_effect=AssertionError('Unexpected OCR')):
                    report = convert(source, output)
                self.assertEqual(report['warnings'], [])
                self.assertEqual(source.read_bytes(), original)
                doc = Document(output)
                joined = '\n'.join(p.text for p in doc.paragraphs)
                for index in range(1, 4):
                    self.assertIn(f'Left paragraph {chr(64+index)}', joined)
                    self.assertIn(f'{index}{punctuation} Ordered entry {chr(64+index)}', joined)
                self.assertLess(joined.index('Left paragraph C'), joined.index('Ordered entry A'))
                doc.paragraphs[-1].add_run(' edited')
                doc.save(root / 'edited.docx')
                self.assertIn('edited', '\n'.join(p.text for p in Document(root / 'edited.docx').paragraphs))

    def test_compact_number_label_status_grid_stays_on_ocr_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.pdf'
            content = b''
            for index, (label, status) in enumerate(zip(
                ['Alpha', 'Beta', 'Gamma'], ['Active', 'Pending', 'Closed']
            ), 1):
                y = 765 - index * 25
                content += text(50, y, f'{index}.') + text(70, y, label) + text(300, y, status)
            fixture(path, content=content)
            with pdfplumber.open(path) as pdf:
                with self.assertRaisesRegex(Rejected, 'Layout needs OCR'):
                    native_page(pdf.pages[0])

    def test_numeric_cells_are_not_all_treated_as_list_markers(self):
        # Vary gaps to avoid regular borderless-table reconstruction. Ambiguous
        # aligned numeric cells must still request OCR, rather than flatten.
        for number, label, gap in [('1.', 'Label', 40), ('1.5', 'Label', 8), ('1.', '123', 8), ('1.', 'Label', 8)]:
            with self.subTest(number=number, label=label, gap=gap), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'source.pdf'
                content = b''
                for index, y in enumerate((720, 680, 640)):
                    content += text(48, y, f'Left prose {index}')
                    content += text(342, y, number)
                    # Helvetica widths at 12pt: digits 6.672, period 3.336.
                    number_width = sum(3.336 if c == '.' else 6.672 for c in number)
                    content += text(342 + number_width + gap, y, label)
                fixture(path, content=content)
                with pdfplumber.open(path) as pdf:
                    with self.assertRaisesRegex(Rejected, 'Layout needs OCR'):
                        native_page(pdf.pages[0])


if __name__ == '__main__':
    unittest.main()
