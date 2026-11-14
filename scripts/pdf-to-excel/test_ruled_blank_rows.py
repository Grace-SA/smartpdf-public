"""Physical empty PDF rows remain explicit empty worksheet rows."""
import os
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
import pdfplumber

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server/pdf-to-excel'))
from convert import convert, ruled_tables, ConversionError


def grid_pdf(path, rows, *, ruled=True, merged=False):
    drawing = canvas.Canvas(str(path),pagesize=(400,500))
    top, step = 450, 30
    if ruled:
        for x in (40,200,360):
            drawing.line(x,top-len(rows)*step,x,top)
        for row in range(len(rows)+1):
            drawing.line(200 if merged and row == 2 else 40,top-row*step,360,top-row*step)
    drawing.setFont('Helvetica',11)
    for row,values in enumerate(rows):
        for x,value in zip((50,210),values):
            drawing.drawString(x,top-row*step-20,value)
    drawing.save()


class RuledBlankRowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root/'synthetic.pdf'
        self.output = self.root/'result.xlsx'

    def tearDown(self):
        self.temp.cleanup()

    def convert_rows(self,rows,layout='tables'):
        grid_pdf(self.source,rows)
        with patch.dict(os.environ,{},clear=True):
            report = convert(self.source,self.output,{'ocr':False,'layout':layout})
        with closing(load_workbook(self.output)) as book:
            values = [[str(value or '') for value in row] for row in book.active.values]
        return report,values

    def test_interior_blank_row_preserves_positions_and_raw_cell_reference(self):
        rows = [['Item','Amount'],['A','0010'],['',''],['B','20.00']]
        report,values = self.convert_rows(rows)
        self.assertEqual(values,rows)
        self.assertEqual(report['preview'][0]['rows'],4)
        self.assertEqual(report['preview'][0]['values'],rows)
        with zipfile.ZipFile(self.output) as archive:
            root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        ns = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        self.assertEqual(root.find(".//s:c[@r='B4']/s:is/s:t",ns).text,'20.00')
        self.assertIsNone(root.find(".//s:c[@r='B3']/s:is/s:t",ns))

    def test_leading_trailing_and_consecutive_blank_rows_are_retained(self):
        rows = [['',''],['Item','Amount'],['A','10'],['',''],['',''],['B','20'],['','']]
        report,values = self.convert_rows(rows)
        self.assertEqual(values,rows)
        self.assertEqual(report['preview'][0]['rows'],len(rows))

    def test_blank_row_geometry_keeps_closed_grid_invariants(self):
        rows = [['Item','Amount'],['A','10'],['',''],['B','20']]
        grid_pdf(self.source,rows)
        with pdfplumber.open(self.source) as source:
            table = ruled_tables(source.pages[0])[0]
        self.assertEqual(table['heights'],[30]*4)
        self.assertEqual(len(table['cells']),8)
        self.assertTrue(table['closedGrid'])
        self.assertEqual(sorted({c['r'] for c in table['cells']}),[0,1,2,3])

    def test_single_sheet_layout_keeps_empty_record_row(self):
        rows = [['Item','Amount'],['A','10'],['',''],['B','20']]
        report,values = self.convert_rows(rows,'single')
        self.assertEqual(values[1:],rows)
        self.assertEqual(report['preview'][0]['values'],rows)

    def test_unruled_whitespace_is_not_invented_as_a_grid_row(self):
        from text_tables import aligned_tables
        drawing = canvas.Canvas(str(self.source),pagesize=(400,500))
        for y,values in zip((450,430,390,370),[['Item','Amount'],['A','10'],['B','20'],['C','30']]):
            for x,value in zip((50,210),values):
                drawing.drawString(x,y,value)
        drawing.save()
        with pdfplumber.open(self.source) as source:
            tables = aligned_tables(source.pages[0])
        self.assertEqual(len(tables),1)
        self.assertEqual(len(tables[0]['heights']),4)

    def test_vertical_merge_across_empty_row_is_preserved(self):
        rows = [['Item','Amount'],['A','10'],['',''],['B','20']]
        grid_pdf(self.source,rows,merged=True)
        with patch.dict(os.environ,{},clear=True):
            convert(self.source,self.output,{'ocr':False})
        with closing(load_workbook(self.output)) as book:
            self.assertEqual(str(next(iter(book.active.merged_cells.ranges))),'A2:A3')
            self.assertEqual(book.active['B4'].value,'20')
            self.assertIsNone(book.active['B3'].value)
            self.assertEqual(book.active.max_row,4)

    def test_empty_grid_remains_rejected(self):
        grid_pdf(self.source,[['','']]*4)
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ConversionError):
                convert(self.source,self.output,{'ocr':False})
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
