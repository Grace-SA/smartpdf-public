"""Generated public synthetic cases; no user files or fixture binaries."""
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, NumberObject, ArrayObject
from docx import Document
from legacy_worker import convert, parse_pdf, export_word, Rejected


def fixture(path, content=b'BT /F1 12 Tf 48 750 Td (Editable 123.45) Tj ET', *, rotation=0, pages=1, crop=False, protected=False):
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
    for _ in range(pages):
        page = writer.add_blank_page(612, 792)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject(); stream.set_data(content)
        page[NameObject('/Contents')] = writer._add_object(stream)
        if rotation:
            page[NameObject('/Rotate')] = NumberObject(rotation)
        if crop:
            page[NameObject('/CropBox')] = ArrayObject([NumberObject(v) for v in (20, 30, 600, 780)])
    if protected:
        writer.encrypt('synthetic-password')
    with path.open('wb') as output:
        writer.write(output)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'synthetic.pdf'
        self.output = self.root / 'output.docx'

    def tearDown(self):
        self.tmp.cleanup()

    def test_editable_text_and_model_geometry(self):
        fixture(self.source, crop=True)
        model = parse_pdf(self.source)
        self.assertEqual(model['schema'], 1)
        page = model['pages'][0]
        self.assertEqual((page['width'], page['height']), (580, 750))
        self.assertEqual(page['blocks'][0]['source'], 'native')
        # PDFium reports the glyph outline, including Helvetica's side bearing.
        self.assertTrue(28 < page['blocks'][0]['bbox'][0] < 30)
        export_word(model, self.output)
        document = Document(self.output)
        self.assertEqual([p.text for p in document.paragraphs], ['Editable 123.45'])
        document.paragraphs[0].add_run(' edited')
        edited = self.root / 'edited.docx'; document.save(edited)
        self.assertEqual(Document(edited).paragraphs[0].text, 'Editable 123.45 edited')
        self.assertAlmostEqual(document.sections[0].page_width.pt, 580, places=1)

    def test_multiple_pages_and_no_overwrite(self):
        fixture(self.source, pages=2)
        self.assertEqual(convert(self.source, self.output)['pages'], 2)
        before = self.output.read_bytes()
        self.assertEqual(len(Document(self.output).sections), 2)
        with self.assertRaises(Rejected):
            convert(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), before)

    def test_whole_file_refusals(self):
        for options in ({'rotation': 90}, {'pages': 201}, {'protected': True},
                        {'content': b''}, {'content': b'0 0 20 20 re f'},
                        {'content': b'BT /F1 12 Tf 3 Tr 48 750 Td (Hidden) Tj ET'},
                        {'content': b'1 1 1 rg BT /F1 12 Tf 48 750 Td (White) Tj ET'},
                        {'content': b'BT /F1 12 Tf 48 750 Td (Left) Tj 250 0 Td (Right) Tj ET'},
                        {'content': b'BT /F1 12 Tf -100 750 Td (Clipped) Tj ET'}):
            with self.subTest(options=options):
                fixture(self.source, **options)
                with self.assertRaises(Rejected): convert(self.source, self.output)
                self.assertFalse(self.output.exists())

    def test_corrupt_file_produces_no_output(self):
        self.source.write_bytes(b'%PDF-1.7\ntruncated')
        with self.assertRaises(Exception): convert(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_two_hundred_text_pages_keep_every_page_in_order(self):
        fixture(self.source, pages=200)
        self.assertEqual(convert(self.source, self.output)['pages'], 200)
        document = Document(self.output)
        self.assertEqual(len(document.sections), 200)
        self.assertEqual(sum(p.text == 'Editable 123.45' for p in document.paragraphs), 200)


if __name__ == '__main__':
    unittest.main()
