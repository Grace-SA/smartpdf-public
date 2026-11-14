"""Cell emphasis is source typography, not a guessed semantic header."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document
from reportlab.pdfgen import canvas
import pdfplumber
from layout import native_page
from worker import convert
from exporter import export_word
from model import Rejected


class NativeCellEmphasisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def source(self, mixed=False):
        path=self.root/'source.pdf';c=canvas.Canvas(str(path),pagesize=(400,400))
        for x in (30,180,350):c.line(x,150,x,350)
        for y in (150,200,250,300,350):c.line(30,y,350,y)
        for i,font in enumerate(('Helvetica-Bold','Helvetica','Helvetica-Oblique','Helvetica-BoldOblique')):
            c.setFont(font,12);c.drawString(40,325-50*i,'Label '+str(i+1));c.drawString(190,325-50*i,f'{i+1}.50%')
        if mixed:
            c.setFont('Helvetica',12);c.drawString(95,325,'mixed')
        c.save();return path

    def test_real_native_cells_keep_uniform_styles_without_becoming_headers(self):
        source=self.source();original=source.read_bytes();out=self.root/'result.docx'
        with patch('worker.OCR.recognize',side_effect=AssertionError('unexpected OCR')):
            convert(source,out)
        doc=Document(out);self.assertEqual(len(doc.tables),1)
        for i,flags in enumerate(((True,False),(False,False),(False,True),(True,True))):
            for cell in doc.tables[0].rows[i].cells:
                runs=[r for p in cell.paragraphs for r in p.runs if r.text]
                self.assertTrue(runs)
                self.assertTrue(all((r.bold,r.italic)==flags for r in runs))
            self.assertEqual(doc.tables[0].cell(i,1).text,f'{i+1}.50%')
        with pdfplumber.open(source) as pdf:
            table=next(b for b in native_page(pdf.pages[0]) if b['kind']=='table')
            self.assertTrue(all(c['header'] is False for c in table['cells']))
        self.assertEqual(source.read_bytes(),original)

    def test_mixed_cell_is_not_promoted_by_majority_style(self):
        source=self.source(mixed=True)
        with pdfplumber.open(source) as pdf:
            table=next(b for b in native_page(pdf.pages[0]) if b['kind']=='table')
            cell=next(c for c in table['cells'] if c['row']==0 and c['col']==0)
            self.assertNotIn('bold',cell)
            self.assertFalse(cell['italic'])
            self.assertIn('mixed',cell['text'])
        out=self.root/'mixed.docx';convert(source,out)
        self.assertTrue(all(not r.bold for r in Document(out).tables[0].cell(0,0).paragraphs[0].runs))

    def test_empty_fontname_skips_emphasis_and_unlabelled_names_do_not_add_it(self):
        source=self.source()
        for replacement in ('', 'UnknownFamily'):
            with pdfplumber.open(source) as pdf:
                page=pdf.pages[0]
                for char in page.chars:
                    if 30 < (char['x0']+char['x1'])/2 < 180 and 50 < (char['top']+char['bottom'])/2 < 100:
                        char['fontname']=replacement
                table=next(b for b in native_page(page) if b['kind']=='table')
                cell=next(c for c in table['cells'] if c['row']==0 and c['col']==0)
                if replacement:
                    self.assertFalse(cell['bold']);self.assertFalse(cell['italic'])
                else:
                    self.assertNotIn('bold',cell);self.assertNotIn('italic',cell)

    def test_aligned_blank_records_keep_line_positions_and_emphasis(self):
        source=self.root/'records.pdf';c=canvas.Canvas(str(source),pagesize=(400,400))
        for x in (30,180,350):c.line(x,200,x,350)
        for y in (200,320,350):c.line(30,y,350,y)
        c.setFont('Helvetica',10);c.drawString(40,330,'Record');c.drawString(190,330,'Value')
        for i,y in enumerate((300,280,260,240)):
            c.setFont('Helvetica',10);c.drawString(40,y,('Alpha','Beta','Gamma','Delta')[i])
            if i!=1:
                c.setFont('Helvetica-BoldOblique',10);c.drawString(190,y,str((i+1)*10))
        c.save();out=self.root/'records.docx';convert(source,out)
        cell=Document(out).tables[0].cell(1,1)
        self.assertEqual(cell.text,'10\n\n30\n40')
        self.assertTrue(all(r.bold and r.italic for p in cell.paragraphs for r in p.runs if r.text))
        doc=Document(out);doc.tables[0].cell(1,1).paragraphs[0].add_run(' edited');doc.save(self.root/'edited.docx')
        self.assertEqual(Document(self.root/'edited.docx').tables[0].cell(1,1).text,'10\n\n30\n40 edited')

    def model(self):
        cells=[dict(row=r,col=c,rowspan=1,colspan=1,text=f'{r}{c}.50',header=r==0,size=10) for r in range(2) for c in range(2)]
        return dict(schema=2,pages=[dict(index=0,width=400,height=400,blocks=[dict(id='table',kind='table',bbox=[30,30,350,150],rows=2,cols=2,cells=cells,source='ocr')])],warnings=[])

    def test_ocr_header_default_is_unchanged_and_explicit_false_is_respected(self):
        model=self.model();model['pages'][0]['blocks'][0]['cells'][1]['bold']=False
        out=self.root/'ocr.docx';export_word(model,out,self.root)
        t=Document(out).tables[0]
        self.assertTrue(next(r for r in t.cell(0,0).paragraphs[0].runs if r.text).bold)
        self.assertFalse(next(r for r in t.cell(0,1).paragraphs[0].runs if r.text).bold)

    def test_invalid_emphasis_rejected_before_output(self):
        for flag in ('bold','italic'):
            for value in ('false',1,None,[],float('nan')):
                model=self.model();model['pages'][0]['blocks'][0]['cells'][0][flag]=value
                out=self.root/'invalid.docx'
                with self.assertRaisesRegex(Rejected,'Invalid table cell emphasis'):
                    export_word(model,out,self.root)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
