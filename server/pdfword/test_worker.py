"""Generated public synthetic cases; no user files or fixture binaries."""
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfWriter, PdfReader
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, NumberObject, ArrayObject, TextStringObject
from docx import Document
from worker import convert, parse_pdf, export_word, Rejected


def fixture(path, content=b'BT /F1 12 Tf 48 750 Td (Editable 123.45) Tj ET', *, rotation=0, pages=1, crop=False, protected=False, cjk=False):
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
    if cjk:
        descendant = writer._add_object(DictionaryObject({
            NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/CIDFontType0'),
            NameObject('/BaseFont'): NameObject('/STSong-Light'), NameObject('/DW'): NumberObject(1000),
            NameObject('/CIDSystemInfo'): DictionaryObject({NameObject('/Registry'): TextStringObject('Adobe'),
                NameObject('/Ordering'): TextStringObject('GB1'), NameObject('/Supplement'): NumberObject(4)})}))
        font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type0'), NameObject('/BaseFont'): NameObject('/STSong-Light'),
            NameObject('/Encoding'): NameObject('/UniGB-UCS2-H'),
            NameObject('/DescendantFonts'): ArrayObject([descendant])}))
    for index in range(pages):
        page = writer.add_blank_page(612, 792)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject(); stream.set_data(content(index) if callable(content) else content)
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
        fixture(self.source, pages=200,
                content=lambda index: f'BT /F1 12 Tf 48 750 Td (Page {index + 1:03d} / 200) Tj ET'.encode())
        self.assertEqual(convert(self.source, self.output)['pages'], 200)
        document = Document(self.output)
        self.assertEqual(len(document.sections), 200)
        self.assertEqual([p.text for p in document.paragraphs if p.text],
                         [f'Page {index + 1:03d} / 200' for index in range(200)])

    def test_adjacent_runs_preserve_words_spaces_and_numbers(self):
        cases = [
            (b'(Hello ) Tj (world) Tj', 'Hello world'),
            (b'(Ed) Tj (it) Tj (able) Tj', 'Editable'),
            (b'(Amount: ) Tj (123) Tj (.45) Tj', 'Amount: 123.45'),
            (b'[(123) -100] TJ (.45) Tj', '123.45'),
            (b'[(Hello) -300] TJ (world) Tj', 'Hello world'),
            (b'(Hello ) Tj /F1 14 Tf (world) Tj', 'Hello world'),
            (b'(Hello ) Tj 0.5 Ts (world) Tj', 'Hello world'),
            (b'[(A) 80 (V) -250 (test)] TJ', 'AV test'),
        ]
        for content, expected in cases:
            with self.subTest(expected=expected, content=content):
                fixture(self.source, content=b'BT /F1 12 Tf 48 750 Td ' + content + b' ET')
                model = parse_pdf(self.source)
                self.assertEqual([block['text_raw'] for block in model['pages'][0]['blocks']], [expected])
                output = self.root / f'editable-{cases.index((content, expected))}.docx'
                export_word(model, output)
                self.assertEqual([p.text for p in Document(output).paragraphs], [expected])

    def test_glyph_positioning_and_staggered_columns_are_refused(self):
        cases = [
            b'BT /F1 12 Tf 48 750 Td [(Left) -20000 (Right)] TJ ET',
            b'BT /F1 12 Tf -8 Tc 48 750 Td (SECRET OVERLAP) Tj ET',
            b'BT /F1 12 Tf 48 750 Td [(First) 4000 (Second)] TJ ET',
            (b'BT /F1 12 Tf 48 750 Td (left first) Tj ET '
             b'BT /F1 12 Tf 300 730 Td (right first) Tj ET '
             b'BT /F1 12 Tf 48 710 Td (left second) Tj ET '
             b'BT /F1 12 Tf 300 690 Td (right second) Tj ET'),
        ]
        for index, content in enumerate(cases):
            with self.subTest(content=content):
                fixture(self.source, content=content)
                output = self.root / f'refused-{index}.docx'
                with self.assertRaises(Rejected):
                    convert(self.source, output)
                self.assertFalse(output.exists())

    def test_numeric_fragments_match_independent_parser(self):
        cases = ('123.45', '-0.25', '1,234.56', '2026-11-11', 'INV-001', '50%', 'USD 99.90')
        for index, expected in enumerate(cases):
            with self.subTest(expected=expected):
                content = b'BT /F1 12 Tf 48 750 Td ' + b' '.join(
                    b'(' + character.encode() + b') Tj' for character in expected) + b' ET'
                fixture(self.source, content=content)
                self.assertEqual(PdfReader(self.source).pages[0].extract_text().strip(), expected)
                output = self.root / f'number-{index}.docx'
                convert(self.source, output)
                self.assertEqual([p.text for p in Document(output).paragraphs], [expected])

    def test_late_unsupported_page_does_not_publish_partial_word(self):
        fixture(self.source, pages=3, content=lambda index:
                b'BT /F1 12 Tf 48 750 Td [(Left) -20000 (Right)] TJ ET' if index == 2 else
                b'BT /F1 12 Tf 48 750 Td (Supported text) Tj ET')
        with self.assertRaises(Rejected):
            convert(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_chinese_runs_match_independent_pdf_reader_and_remain_editable(self):
        text = '中文财务报告'
        content = b'BT /F1 12 Tf 48 750 Td ' + b' '.join(
            b'<' + part.encode('utf-16-be').hex().encode() + b'> Tj'
            for part in ('中文', '财务', '报告')) + b' ET'
        fixture(self.source, content=content, cjk=True)
        self.assertEqual(PdfReader(self.source).pages[0].extract_text().strip(), text)
        convert(self.source, self.output)
        document = Document(self.output)
        self.assertEqual([p.text for p in document.paragraphs], [text])
        document.paragraphs[0].add_run(' 已编辑')
        edited = self.root / 'chinese-edited.docx'
        document.save(edited)
        self.assertEqual(Document(edited).paragraphs[0].text, text + ' 已编辑')


if __name__ == '__main__':
    unittest.main()
