"""Indexed text registers need column geometry and an independent header rule."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from docx import Document
from reportlab.pdfgen import canvas
from layout import borderless_tables
from worker import convert


class IndexedTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def source(self, *, rule='good', keys=('1','2','3','4'), shift=False,
               extra=False, missing=False, header_shift=False, cols=3, pages=1):
        path = self.root/'source.pdf'
        c = canvas.Canvas(str(path), pagesize=(600,600))
        for page in range(pages):
            c.setFont('Helvetica',10)
            xs=(40,200,390)[:cols]
            for j,text in enumerate(('Number','Item','Status')[:cols]):
                c.drawString(xs[j]+(190 if header_shift and j==0 else 3),550,text)
            if rule!='none':
                c.setLineWidth(0.5)
                if rule=='white':c.setStrokeColorRGB(1,1,1)
                if rule=='transparent':c.setStrokeAlpha(0)
                c.line(40,530 if rule=='misplaced' else 543,
                       220 if rule=='short' else 550,530 if rule=='misplaced' else 543)
            if rule=='covered':
                c.setFillColorRGB(1,1,1);c.rect(38,541,514,4,stroke=0,fill=1);c.setFillColorRGB(0,0,0)
            for i,key in enumerate(keys):
                for j,text in enumerate((key,'Item '+str(i),'Ready')[:cols]):
                    if missing and i==3 and j==2:continue
                    c.drawString(xs[j]+(8 if shift and i==2 and j==1 else 0),530-16*i,text)
            if extra:c.drawString(200,530-16*len(keys),'continued detail')
            c.showPage()
        c.save();return path

    def tables(self,path):
        with pdfplumber.open(path) as doc:
            return [borderless_tables(p.extract_words(return_chars=True),p) for p in doc.pages]

    def test_real_pdf_full_conversion_keeps_pages_cells_and_editability(self):
        path=self.source(pages=2);original=path.read_bytes();out=self.root/'result.docx'
        with patch('worker.OCR.recognize',side_effect=AssertionError('unexpected OCR')):
            convert(path,out)
        doc=Document(out);self.assertEqual(len(doc.tables),2)
        for table in doc.tables:
            self.assertEqual([[c.text for c in row.cells] for row in table.rows],
                             [['Number','Item','Status']]+[[str(i+1),'Item '+str(i),'Ready'] for i in range(4)])
        doc.tables[1].cell(4,2).text='Edited';doc.save(out)
        self.assertEqual(Document(out).tables[1].cell(4,2).text,'Edited')
        self.assertEqual(path.read_bytes(),original)

    def test_rule_is_required_and_must_span_columns_between_header_and_body(self):
        for rule in ('none','short','misplaced','white','transparent','covered'):
            with self.subTest(rule=rule):self.assertEqual(self.tables(self.source(rule=rule)),[[]])

    def test_failed_render_is_not_positive_rule_evidence(self):
        with patch('pdfplumber.page.Page.to_image',side_effect=RuntimeError('render unavailable')):
            self.assertEqual(self.tables(self.source()),[[]])

    def test_many_candidate_rules_cannot_repeat_unbounded_pixel_work(self):
        source=self.source(rule='white')
        with pdfplumber.open(source) as pdf:
            page=pdf.pages[0]
            line=page.lines[0]
            page._objects['line']=[dict(line) for _ in range(100)]
            rendered=page.to_image(resolution=144)
            gray=rendered.original.convert('L')
            with patch.object(page,'to_image',return_value=rendered) as render, \
                 patch.object(rendered.original,'convert',return_value=gray) as convert_gray, \
                 patch.object(gray,'load',wraps=gray.load) as probe:
                self.assertEqual(borderless_tables(page.extract_words(return_chars=True),page),[])
                self.assertEqual(render.call_count,1)
                self.assertEqual(convert_gray.call_count,1)
                self.assertEqual(probe.call_count,32)

    def test_keys_are_consecutive_unmodified_positive_integer_labels(self):
        for keys in (('1','2','4','5'),('1','2','1','2'),('01','02','03','04'),
                     ('1.','2.','3.','4.'),('1)','2)','3)','4)'),('1','2')):
            with self.subTest(keys=keys):self.assertEqual(self.tables(self.source(keys=keys)),[[]])

    def test_misaligned_missing_continued_or_two_column_rows_still_rejected(self):
        for kwargs in ({'shift':True},{'missing':True},{'extra':True},{'header_shift':True},{'cols':2}):
            with self.subTest(kwargs=kwargs):self.assertEqual(self.tables(self.source(**kwargs)),[[]])


if __name__=='__main__':unittest.main()
