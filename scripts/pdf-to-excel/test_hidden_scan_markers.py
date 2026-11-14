"""Source-generated proof boundaries for marked, cropped hidden OCR scans."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server/pdf-to-excel'))
from test_source_hidden_ocr import fixture, scanned_table
import source_hidden_ocr as m

MARK = b'/Suspect << /Conf 0 >> BDC '
END = b' EMC '
HIDDEN = b'BT /F1 12 Tf 3 Tr (19.50) Tj ET'


def bytes_of(page):
    writer = PdfWriter(); writer.add_page(page); out = io.BytesIO(); writer.write(out)
    return out.getvalue()


def marked_scan(*, clipped=False, covered=False):
    page = PdfReader(io.BytesIO(scanned_table(True))).pages[0]
    raw = page.get_contents().get_data()
    prefix = b'q 0 0 1 1 re W* n ' if clipped else b''
    suffix = b' Q' if clipped else b''
    if covered:
        suffix += b' q 1 G 600 w 0 300 m 600 300 l S Q'
    stream = DecodedStreamObject()
    stream.set_data(prefix + MARK + raw + END + suffix)
    page[NameObject('/Contents')] = stream
    page.cropbox.lower_left = (1, 1)
    page.cropbox.upper_right = (599, 599)
    return page


class MarkedScanTests(unittest.TestCase):
    def test_valid_metadata_nested_and_cropped(self):
        page = fixture(MARK * 3 + HIDDEN + END * 3)
        page.cropbox.lower_left = (10, 10)
        page.cropbox.upper_right = (290, 190)
        self.assertEqual(m.classify(page), 'hidden')
        page.cropbox.upper_right = (301, 200)
        self.assertEqual(m.classify(page), 'other')

    def test_mixed_visible_and_restored_state(self):
        for text in [
            MARK + HIDDEN + END + b'BT /F1 12 Tf 0 Tr (visible) Tj ET',
            b'BT /F1 12 Tf 0 Tr ET q ' + HIDDEN + b' Q BT (visible) Tj ET',
        ]:
            self.assertEqual(m.classify(fixture(text)), 'other')
        for mode in range(4, 8):
            self.assertEqual(m.classify(fixture(HIDDEN.replace(b'3 Tr', str(mode).encode()+b' Tr'))), 'unsupported')

    def test_markers_span_content_streams_not_graphics_stack(self):
        page = fixture(MARK + b' q ' + HIDDEN)
        tail = DecodedStreamObject(); tail.set_data(b' Q '+END)
        page[NameObject('/Contents')] = ArrayObject([page['/Contents'], tail])
        self.assertEqual(m.classify(page), 'hidden')
        tail.set_data(b' Q '+END+b' BT /F1 12 Tf (visible) Tj ET')
        self.assertEqual(m.classify(page), 'other')

    def test_unknown_or_malformed_markers_decline(self):
        for prefix, suffix in [
            (b'/OC << /Conf 0 >> BDC ', END),
            (b'/Suspect << /ActualText (secret) >> BDC ', END),
            (b'/Suspect /Props BDC ', END),
            (b'/Suspect << /Conf -1 >> BDC ', END),
            (b'/Suspect << /Conf 2 >> BDC ', END),
            (b'/Suspect << /Conf true >> BDC ', END),
            (b'/Suspect << /Conf 0 /Other 1 >> BDC ', END),
            (b'(Suspect) << /Conf 0 >> BDC ', END),
            (MARK, b''), (b'', END),
            (MARK * 65, END * 65),
            (b'/GS1 gs ', b''),
        ]:
            with self.subTest(prefix=prefix[:50]):
                self.assertEqual(m.classify(fixture(prefix+HIDDEN+suffix)), 'unsupported')

    def test_narrow_paths_and_invalid_sequences(self):
        good = b'q 1 w 0 0 300 200 re W* n 0 0 m 300 200 l S Q '
        self.assertEqual(m.classify(fixture(prefix=good)), 'hidden')
        for prefix in [b'-1 w ', b'1 2 l ', b'W* ', b'0 0 m ',
                       b'0 0 1 1 re W* W* n ', b'0 0 1 1 re f ',
                       b'BT 0 0 m ET ', b'10000001 0 m 0 0 l S ']:
            self.assertEqual(m.classify(fixture(prefix=prefix)), 'unsupported')

    def test_final_render_not_embedded_image_for_cover_and_clip(self):
        import fitz
        from PIL import Image
        for clipped, covered in [(True, False), (False, True)]:
            with self.subTest(clipped=clipped):
                page = marked_scan(clipped=clipped, covered=covered)
                self.assertEqual(m.classify(page), 'hidden')
                document = fitz.open(stream=bytes_of(page), filetype='pdf')
                pix = document[0].get_pixmap()
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                self.assertEqual(image.getextrema(), ((255,255),)*3)
                document.close()

    def test_final_covered_and_clipped_pages_reject_in_actual_conversion(self):
        from convert import convert, ConversionError
        for clipped, covered in [(True, False), (False, True)]:
            with self.subTest(clipped=clipped), tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / 'covered.pdf'
                target = Path(folder) / 'out.xlsx'
                source.write_bytes(bytes_of(marked_scan(clipped=clipped, covered=covered)))
                # Exercise real PDFium rasterization and RapidOCR. No layout
                # model is needed to certify that this blank page has no table.
                with patch.dict(os.environ, {'PDF_EXCEL_MODELS': ''}):
                    with self.assertRaisesRegex(ConversionError, 'No reliable table'):
                        convert(source, target, {'ocr': True})
                self.assertFalse(target.exists())

    def test_routing_is_ocr_only_and_ocr_failure_never_uses_hidden_layer(self):
        from convert import convert, ConversionError
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'scan.pdf'; target = Path(folder)/'out.xlsx'
            source.write_bytes(bytes_of(marked_scan()))
            with self.assertRaisesRegex(ConversionError, 'needs OCR'):
                convert(source, target, {'ocr': False})
            self.assertFalse(target.exists())
            with patch('convert.scan_tables', side_effect=ConversionError('OCR failed')):
                with self.assertRaisesRegex(ConversionError, 'OCR failed'):
                    convert(source, target, {'ocr': True})
            self.assertFalse(target.exists())
            result = convert(source, target, {'ocr': True})
            self.assertEqual(result['ocrPages'], [1])
            book = load_workbook(target)
            try:
                values = [c.value for row in book.active for c in row]
                self.assertIn('12.50', values)
                self.assertNotIn('19.50', values)
            finally:
                book.close()

if __name__ == '__main__':
    unittest.main()
