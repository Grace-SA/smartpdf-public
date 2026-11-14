"""Mixed wrapped/unwrapped agenda items need evidence from the complete sequence."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from docx import Document
from reportlab.pdfgen import canvas
from layout import native_page
from model import Rejected
from worker import convert


class NativeAgendaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def source(self, keys=('1.','2.','3.','4.','5.','6.'), wrapped=(1,2),
               status=False, body_status=False, body_x=80, extra_same_item=False):
        path=self.root/'source.pdf';c=canvas.Canvas(str(path),pagesize=(612,792))
        c.setFont('Helvetica',12)
        c.drawString(40,760,'Meeting venue');c.drawString(400,760,'Planning date')
        for i,key in enumerate(keys):
            y=700-i*60
            c.drawString(50,y,key);c.drawString(80,y,'Agenda topic '+chr(65+i))
            if status:c.drawString(500,y,'Pending')
            if i in wrapped:
                c.drawString(body_x,y-14,'Detailed supporting prose explains the topic for every attendee.')
                if body_status:c.drawString(500,y-14,'Status')
                if extra_same_item:c.drawString(body_x,y-28,'Additional supporting prose belongs to this same agenda item.')
        c.drawString(80,350,'2.1 Preserve nested item and section 54957')
        c.drawString(50,330,'`')
        c.save();return path

    def test_agenda_keeps_all_items_nested_numbers_and_punctuation_editable(self):
        source=self.source();original=source.read_bytes();out=self.root/'result.docx'
        with patch('worker.OCR.recognize',side_effect=AssertionError('unexpected OCR')):
            convert(source,out)
        doc=Document(out);text='\n'.join(p.text for p in doc.paragraphs)
        positions=[text.index(f'{i+1}. Agenda topic {chr(65+i)}') for i in range(6)]
        self.assertEqual(positions,sorted(positions));self.assertIn('2.1 Preserve nested item and section 54957',text)
        self.assertIn('`',text);self.assertEqual(len(doc.tables),0)
        self.assertEqual(source.read_bytes(),original)
        doc.paragraphs[-1].add_run(' edited');doc.save(out)
        self.assertIn('edited',Document(out).paragraphs[-1].text)

    def test_single_line_or_one_item_continuations_are_not_group_evidence(self):
        for kwargs in ({'wrapped':()},{'wrapped':(1,)},{'wrapped':(1,),'extra_same_item':True}):
            with self.subTest(kwargs=kwargs):self.assert_rejected(self.source(**kwargs))

    def test_entire_number_sequence_must_match_without_choosing_a_prefix(self):
        for keys in (('1.','2.','3.','4.','4.','5.'),('1.','2.','3.','4.','6.','7.'),
                     ('1.','2.','3.','4.','6.','5.'),('1.','2.','3.','4.','5)','6.')):
            with self.subTest(keys=keys):self.assert_rejected(self.source(keys=keys))

    def test_independent_columns_or_incorrect_indent_do_not_supply_prose_evidence(self):
        for kwargs in ({'status':True},{'body_status':True},{'body_x':300},{'body_x':40}):
            with self.subTest(kwargs=kwargs):self.assert_rejected(self.source(**kwargs))

    def assert_rejected(self,source):
        with pdfplumber.open(source) as pdf:
            with self.assertRaisesRegex(Rejected,'Layout needs OCR'):
                native_page(pdf.pages[0])


if __name__=='__main__':unittest.main()
