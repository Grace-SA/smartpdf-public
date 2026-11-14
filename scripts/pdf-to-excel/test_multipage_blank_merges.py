"""End-to-end native multi-page row, merge and page-context integrity."""
import os
import importlib.util
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from reportlab.pdfgen import canvas
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server/pdf-to-excel'))
from convert import convert


def multipage_pdf(path):
    drawing = canvas.Canvas(str(path),pagesize=(400,500))
    for page in range(1,4):
        drawing.setFont('Helvetica',11)
        drawing.drawString(40,480,f'Synthetic page {page} context')
        # Five explicitly ruled rows; one blank row plus a two-row left-cell merge.
        for x in (40,200,360):
            drawing.line(x,260,x,450)
        levels = (450,420,390,350,310,260)
        for row,y in enumerate(levels):
            drawing.line(200 if row == 3 and page != 2 else 40,y,360,y)
        rows = [['ID','Value'],['',''],[f'Group {page}',f'000{page}'],
                ['',f'{page}.50'],[f'Tail {page}',f'{page}000.00']]
        for row,values in enumerate(rows):
            for x,value in zip((50,210),values):
                drawing.drawString(x,levels[row]-20,value)
        drawing.showPage()
    drawing.save()


class MultiPageBlankMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/'synthetic.pdf'
        self.output = self.root/'output.xlsx'
        multipage_pdf(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def check_layout(self,layout,selected='all',pages=(1,2,3),ocr=False):
        with patch.dict(os.environ,{},clear=True):
            report = convert(self.source,self.output,{'layout':layout,'ocr':ocr,'pages':selected})
        self.assertEqual(report['pages'],len(pages))
        self.assertEqual(report['tables'],len(pages))
        self.assertEqual(report['missingPages'],[])
        self.assertEqual(report['ocrPages'],list(pages) if ocr else [])
        self.assertEqual([p['rows'] for p in report['preview']],[5]*len(pages))
        with closing(load_workbook(self.output)) as book:
            self.assertEqual(len(book.worksheets),1 if layout=='single' else len(pages))
            for position,page in enumerate(pages):
                sheet = book.active if layout=='single' else book.worksheets[position]
                offset = position*8+1 if layout=='single' else 0
                self.assertIsNone(sheet.cell(offset+2,1).value)
                self.assertIsNone(sheet.cell(offset+2,2).value)
                self.assertEqual(sheet.cell(offset+1,1).value,'ID')
                self.assertEqual(sheet.cell(offset+1,2).value,'Value')
                self.assertEqual(sheet.cell(offset+5,1).value,f'Tail {page}')
                self.assertEqual(sheet.cell(offset+3,1).value,f'Group {page}')
                self.assertEqual(sheet.cell(offset+3,2).value,f'000{page}')
                self.assertIsNone(sheet.cell(offset+4,1).value)
                self.assertEqual(sheet.cell(offset+4,2).value,f'{page}.50')
                self.assertEqual(sheet.cell(offset+5,2).value,f'{page}000.00')
                refs = {str(r) for r in sheet.merged_cells.ranges}
                expected = {f'A{p*8+4}:A{p*8+5}' for p,n in enumerate(pages) if n != 2} if layout=='single' else ({'A3:A4'} if page != 2 else set())
                self.assertEqual(refs,expected)
                context = sheet.cell(offset+1,1).comment.text
                self.assertIn(f'Synthetic page {page} context',context)
                for other in {1,2,3}-{page}:
                    self.assertNotIn(f'Synthetic page {other} context',context)
        # Check serialized merge destinations independently of the workbook reader.
        with zipfile.ZipFile(self.output) as archive:
            ns = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            for i,page in enumerate(pages):
                tree = ET.fromstring(archive.read(f'xl/worksheets/sheet{1 if layout=="single" else i+1}.xml'))
                offset = i*8+1 if layout=='single' else 0
                refs = {m.get('ref') for m in tree.findall('.//s:mergeCell',ns)}
                expected = {f'A{p*8+4}:A{p*8+5}' for p,n in enumerate(pages) if n != 2} if layout=='single' else ({'A3:A4'} if page != 2 else set())
                self.assertEqual(refs,expected)

    def test_separate_sheets_keep_empty_rows_merges_and_page_context(self):
        self.check_layout('tables')

    def test_single_sheet_keeps_empty_rows_merges_and_page_context(self):
        self.check_layout('single')

    @unittest.skipUnless(importlib.util.find_spec('rapidocr_onnxruntime') and importlib.util.find_spec('cv2'), 'Requires real OCR dependencies')
    def test_scanned_multipage_grid_keeps_blank_rows_and_merges(self):
        import pypdfium2 as pdf
        from reportlab.lib.utils import ImageReader
        scan = self.root/'scan.pdf'
        drawing = canvas.Canvas(str(scan),pagesize=(400,500))
        with pdf.PdfDocument(self.source) as document:
            for i in range(len(document)):
                with closing(document[i]) as page, closing(page.render(scale=2)) as bitmap:
                    image = bitmap.to_pil().copy()
                drawing.drawImage(ImageReader(image),0,0,width=400,height=500)
                drawing.showPage()
        drawing.save()
        self.source = scan
        self.check_layout('single',ocr=True)

    def test_selected_nonconsecutive_pages_keep_original_page_identity(self):
        self.check_layout('single','1,3',(1,3))


if __name__=='__main__':
    unittest.main()
