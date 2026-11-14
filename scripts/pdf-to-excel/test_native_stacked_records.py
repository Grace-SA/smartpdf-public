"""Native-only extraction must not flatten multiple logical numeric records."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from reportlab.pdfgen import canvas
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server/pdf-to-excel'))
from convert import convert, stacked_numeric_records, ConversionError


def fixture(path, *, numeric_columns=2, preceding_page=False):
    drawing=canvas.Canvas(str(path),pagesize=(400,400))
    if preceding_page:
        for y in (300,330,360):drawing.line(40,y,360,y)
        for x in (40,200,360):drawing.line(x,300,x,360)
        for x,y,text in ((50,340,'Item'),(210,340,'Value'),(50,310,'A'),(210,310,'001')):
            drawing.drawString(x,y,text)
        drawing.showPage()
    for y in (180,210,330,360):drawing.line(40,y,360,y)
    for x in (40,150,250,360):drawing.line(x,180,x,360)
    for x,text in ((50,'Record'),(160,'First'),(260,'Second')):drawing.drawString(x,340,text)
    for i in range(4):
        for x,text in ((50,f'Entry {i+1}'),(160,f'{i+1}.25'),(260,f'{i+2}.50' if numeric_columns==2 else f'Note {i+1}')):
            # Deliberately omit one amount; positional splitting would be unsafe.
            if x==160 and i==3:continue
            drawing.drawString(x,310-i*25,text)
    for x,text in ((50,'Total'),(160,'6.75'),(260,'18.00')):drawing.drawString(x,190,text)
    drawing.save()


class NativeStackedTests(unittest.TestCase):
    def test_detection_requires_distinct_columns_in_same_row(self):
        def cell(r,c,text):return dict(r=r,c=c,rs=1,cs=1,text=text)
        numeric='1.25\n2.50\n3.75'
        self.assertTrue(stacked_numeric_records({'cells':[cell(1,1,numeric),cell(1,2,numeric)]}))
        self.assertFalse(stacked_numeric_records({'cells':[cell(1,1,numeric),cell(2,2,numeric)]}))
        self.assertFalse(stacked_numeric_records({'cells':[cell(1,1,numeric),cell(1,1,numeric)]}))
        self.assertFalse(stacked_numeric_records({'cells':[cell(1,1,numeric),cell(1,2,'wrapped\nordinary\nprose')]}))
        self.assertFalse(stacked_numeric_records({'cells':[cell(1,1,'1\n2'),cell(1,2,'3\n4')]}))
        self.assertFalse(stacked_numeric_records({'cells':[dict(cell(1,1,numeric),rs=2),cell(1,2,numeric)]}))
        self.assertFalse(stacked_numeric_records({'cells':[dict(cell(1,1,numeric),cs=2),cell(1,3,numeric)]}))

    def test_single_numeric_stack_remains_outside_this_narrow_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf';output=Path(tmp)/'result.xlsx';fixture(source,numeric_columns=1)
            with patch.dict(os.environ,{},clear=True):convert(source,output,{'ocr':False})
            book=load_workbook(output)
            self.assertIn('1.25',book.active['B2'].value)
            self.assertIn('Note 4',book.active['C2'].value)
            book.close()

    def test_real_native_conversion_refuses_ambiguous_numeric_stacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf';output=Path(tmp)/'result.xlsx';fixture(source)
            with patch.dict(os.environ,{},clear=True):
                with self.assertRaisesRegex(ConversionError,'row alignment needs the table recognition models'):
                    convert(source,output,{'ocr':False})
            self.assertFalse(output.exists())

    def test_late_page_refusal_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf';output=Path(tmp)/'result.xlsx';fixture(source,preceding_page=True)
            output.write_bytes(b'previous-output')
            with patch.dict(os.environ,{},clear=True):
                with self.assertRaisesRegex(ConversionError,'row alignment'):
                    convert(source,output,{'ocr':False})
            self.assertEqual(output.read_bytes(),b'previous-output')


if __name__=='__main__':unittest.main()
