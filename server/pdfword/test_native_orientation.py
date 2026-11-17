"""Synthetic orientation, editable margins and clipping guards."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pdfplumber
import pypdfium2 as pdf
from test_worker import fixture
from native_orientation import normalize_orientation
from worker import parse_pdf, needs_ocr
from model import Rejected
from exporter import export_word
from docx import Document


class NativeOrientationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root/'source.pdf'

    def tearDown(self):
        self.tmp.cleanup()

    def test_native_right_angle_is_editable_and_original_bytes_stay_unchanged(self):
        fixture(self.source, content=b'BT /F1 12 Tf 0 1 -1 0 300 100 Tm (A sufficiently long native sentence with numbers 12345) Tj ET')
        original = self.source.read_bytes()
        source, corrected = normalize_orientation(self.source, self.root)
        self.assertEqual(corrected, [0])
        self.assertNotEqual(source, self.source)
        model = parse_pdf(self.source, self.root)
        self.assertTrue(all(b['source'] == 'native' for b in model['pages'][0]['blocks']))
        export_word(model, self.root/'result.docx', self.root)
        self.assertIn('12345', ''.join(p.text for p in Document(self.root/'result.docx').paragraphs))
        self.assertEqual(self.source.read_bytes(), original)

    def test_mixed_body_directions_keep_ocr_route(self):
        fixture(self.source, content=b'BT /F1 12 Tf 0 1 -1 0 300 100 Tm (A sufficiently long vertical sentence 12345) Tj ET BT /F1 12 Tf 40 600 Td (Horizontal body text) Tj ET')
        self.assertEqual(normalize_orientation(self.source, self.root), (self.source, []))

    def test_hidden_text_does_not_decide_page_direction(self):
        fixture(self.source, content=b'BT /F1 12 Tf 3 Tr 0 1 -1 0 300 100 Tm (A hidden OCR layer with sufficient characters 12345) Tj ET')
        self.assertEqual(normalize_orientation(self.source, self.root), (self.source, []))

    def test_margin_label_stays_editable_after_direction_correction(self):
        fixture(self.source, content=b'BT /F1 12 Tf 0 1 -1 0 300 100 Tm (A sufficiently long native sentence with numbers 12345) Tj ET BT /F1 10 Tf 300 25 Td (42) Tj ET')
        model = parse_pdf(self.source, self.root)
        text = ''.join(b.get('text', '') for b in model['pages'][0]['blocks'])
        self.assertIn('42', text)
        self.assertIn('12345', text)

    def test_partially_clipped_text_still_requires_ocr(self):
        fixture(self.source, content=b'q 40 740 40 20 re W n BT /F1 12 Tf 40 750 Td (Visible and clipped content) Tj ET Q')
        with pdf.PdfDocument(self.source) as document:
            page = document[0]
            self.assertTrue(needs_ocr(page)[0])
            page.close()

    def test_cancel_during_orientation_does_not_produce_output(self):
        fixture(self.source)
        cancel = self.root/'cancel'
        cancel.touch()
        with self.assertRaisesRegex(Rejected, 'cancelled'):
            normalize_orientation(self.source, self.root, cancel)

    def test_pixel_difference_refuses_orientation_candidate(self):
        fixture(self.source, content=b'BT /F1 12 Tf 0 1 -1 0 300 100 Tm (A sufficiently long native sentence with numbers 12345) Tj ET')
        with patch('native_orientation.ImageChops.difference') as diff:
            diff.return_value.__enter__.return_value.getbbox.return_value = (1, 1, 2, 2)
            self.assertEqual(normalize_orientation(self.source, self.root), (self.source, []))
