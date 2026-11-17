"""Editable content and pagination controls, using synthetic source geometry."""
import tempfile
import unittest
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from exporter import export_word, add_table
from layout import font_family
import test_margin_glyphs as margins


class PaginationTests(unittest.TestCase):
    def test_empty_section_carriers_do_not_inherit_body_spacing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pages = [margins.MarginGlyphTests.page(self, i, True) for i in range(3)]
            export_word(dict(schema=2, pages=pages), root/'result.docx', root)
            document = Document(root/'result.docx')
            carriers = [p for p in document.paragraphs if p._p.find('./'+qn('w:pPr')+'/'+qn('w:sectPr')) is not None]
            self.assertEqual(len(carriers), 2)
            for paragraph in carriers:
                self.assertEqual(paragraph.text, '')
                self.assertEqual(paragraph.paragraph_format.line_spacing.pt, 1)
                self.assertEqual(paragraph.paragraph_format.space_after.pt, 0)
            self.assertEqual([s.footer.paragraphs[0].text for s in document.sections], ['Footer 0','Footer 1','Footer 2'])
            self.assertEqual([p.text for p in document.paragraphs if p.text], ['Body page 0','Body page 1','Body page 2'])

    def test_multiline_header_keeps_full_content_and_repeats_as_a_group(self):
        document = Document()
        block = dict(cols=2, rows=4, header_rows=2, widths=[60,100], cells=[
            dict(row=r,col=c,rowspan=1,colspan=1,text=f'Heading {r}\nSecond line' if r<2 else f'Value {r}-{c}',size=9,font='Times New Roman',bold=False,header=r<2)
            for r in range(4) for c in range(2)])
        table = add_table(document, block, 300)
        self.assertEqual(table.cell(0,0).text, 'Heading 0\nSecond line')
        for index,row in enumerate(table.rows):
            self.assertEqual(row._tr.trPr.find(qn('w:tblHeader')) is not None,index<2)
            for cell in row.cells:
                p=cell.paragraphs[0]
                self.assertEqual(p.paragraph_format.line_spacing,1)
                self.assertFalse(p.paragraph_format.widow_control)
                self.assertEqual(p.runs[0].font.name,'Times New Roman')
                self.assertFalse(p.runs[0].bold)
                if index<2:self.assertTrue(p.paragraph_format.keep_with_next)
            self.assertIsNone(row._tr.trPr.find(qn('w:trHeight')), 'No exact row height may clip text')

    def test_font_mapping_is_conservative(self):
        self.assertEqual(font_family(['abc+timesnewromanpsmt']), 'Times New Roman')
        self.assertEqual(font_family(['couriernew']), 'Courier New')
        self.assertEqual(font_family(['timesroman','unrecognized']), 'Arial')
        self.assertEqual(font_family([]), 'Arial')
