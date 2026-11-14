import copy
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import pdfplumber
from reportlab.pdfgen import canvas
from openpyxl import load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from source_header_warning import split_header_phrase, NOTICE
from convert import write_workbook


class HeaderWarningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def fixture(self, gap=40, right_y=250, title='Annual estimates', phrase='(in thousands)', split=True, inner_gap=0):
        path=self.root/'source.pdf';c=canvas.Canvas(str(path),pagesize=(600,300))
        c.setFont('Helvetica',12);c.drawString(30,250,title)
        end=30+c.stringWidth(title,'Helvetica',12);start=end+gap
        parts=phrase.split(' ',1);c.drawString(start,250,parts[0])
        second=start+c.stringWidth(parts[0]+' ','Helvetica',12)+inner_gap
        c.drawString(second,right_y,parts[1]);c.save()
        doc=pdfplumber.open(path);self.addCleanup(doc.close);page=doc.pages[0]
        words=page.extract_words(x_tolerance=2,y_tolerance=3)
        cut=second if split else start
        groups=[[w for w in words if w['x0']<cut-.1],[w for w in words if w['x0']>=cut-.1]]
        cells=[]
        for i,g in enumerate(groups):
            cells.append(dict(r=0,c=0 if i==0 else 3,rs=1,cs=3 if i==0 else 1,
                              text=' '.join(w['text'] for w in g),sourceTextCandidate=[min(w['x0'] for w in g),min(w['top'] for w in g),max(w['x1'] for w in g),max(w['bottom'] for w in g)]))
        table=dict(cells=cells,widths=[100]*4,heights=[20],bbox=[20,35,550,70],method='layout',page=1,index=1)
        return page,table

    def test_detects_without_mutating_cells(self):
        page,t=self.fixture();before=copy.deepcopy(t)
        self.assertTrue(split_header_phrase(t,page));self.assertEqual(before,t)

    def test_complete_metadata_and_title_are_not_flagged(self):
        page,t=self.fixture(split=False);self.assertFalse(split_header_phrase(t,page))

    def test_ordinary_contiguous_parenthesized_title_not_flagged(self):
        page,t=self.fixture(gap=3);self.assertFalse(split_header_phrase(t,page))

    def test_independent_parentheses_not_flagged(self):
        page,t=self.fixture(title='Annual (estimates)',split=False);self.assertFalse(split_header_phrase(t,page))

    def test_other_baseline_or_large_internal_gap_not_flagged(self):
        page,t=self.fixture(right_y=230);self.assertFalse(split_header_phrase(t,page))
        page,t=self.fixture(inner_gap=30)
        self.assertFalse(split_header_phrase(t,page))

    def test_unsupported_or_changed_text_not_flagged(self):
        page,t=self.fixture()
        for mutate in [lambda t:t.update(method='ocr'),lambda t:t['cells'][0].update(rs=2),lambda t:t['cells'][1].update(c=4),lambda t:t['cells'][1].update(text='different)'),lambda t:t['cells'][0].update(sourceTextCandidate=None)]:
            other=copy.deepcopy(t);mutate(other);self.assertFalse(split_header_phrase(other,page))

    def test_native_detector_not_called_for_scan_or_hidden_ocr(self):
        from test_source_hidden_ocr import scanned_table
        from convert import convert
        for hidden in (False, True):
            with self.subTest(hidden=hidden):
                source=self.root/'scan.pdf';source.write_bytes(scanned_table(hidden))
                with patch('source_header_warning.split_header_phrase',side_effect=AssertionError('Do not use native header evidence for OCR')):
                    result=convert(source,self.root/'scan.xlsx',{'ocr':True})
                self.assertEqual(result['ocrPages'],[1])
                self.assertNotIn(NOTICE,result['warnings'])

    def test_warning_preserves_workbook_data_and_existing_context(self):
        page,t=self.fixture();before=copy.deepcopy(t)
        t.update(splitHeaderPhrase=True,sourceContext='Existing context')
        out=self.root/'out.xlsx';write_workbook([t],out,'tables')
        s=load_workbook(out).worksheets[0]
        self.assertEqual(s['A1'].value,before['cells'][0]['text'])
        self.assertEqual(s['D1'].value,before['cells'][1]['text'])
        self.assertEqual([str(x) for x in s.merged_cells],['A1:C1'])
        self.assertIn(NOTICE,s['A1'].comment.text);self.assertIn('Existing context',s['A1'].comment.text)

if __name__=='__main__':unittest.main()
