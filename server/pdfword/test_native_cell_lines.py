"""Original native-table fixtures with multiline record cells."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from docx import Document
from worker import convert, parse_pdf
from test_worker import fixture
from test_native_lists import text
from test_narrow_columns import word
from layout import words_to_blocks


class NativeCellLineTests(unittest.TestCase):
    def test_cell_line_mode_retains_rows_not_prose_joining(self):
        words=[word(value,50,50+i*14,width=60) for i,value in enumerate(['Alpine','Birch','Cedar'])]
        normal=words_to_blocks(words,612,792)
        cells=words_to_blocks(words,612,792,split_columns=False,merge_lines=False)
        self.assertEqual(len(normal),1)
        self.assertEqual([b['text'] for b in cells],['Alpine','Birch','Cedar'])

    def test_native_table_label_and_amount_lines_survive_edit_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.pdf';output=root/'out.docx'
            commands=b''
            for y in (600,650,675):commands+=f'48 {y} m 330 {y} l S '.encode()
            for x in (48,190,330):commands+=f'{x} 600 m {x} 675 l S '.encode()
            commands+=text(55,658,'District')+text(200,658,'Amount')
            for y,label,amount in [(635,'Alpine','12.34'),(621,'Birch','-56.78'),(607,'Cedar','0.00')]:
                commands+=text(55,y,label)+text(200,y,amount)
            fixture(source,content=commands)
            original=source.read_bytes()
            with patch('worker.OCR.recognize',side_effect=AssertionError('Unexpected OCR')):
                convert(source,output)
            self.assertEqual(source.read_bytes(),original)
            doc=Document(output);table=doc.tables[0]
            self.assertEqual(table.cell(1,0).text,'Alpine\nBirch\nCedar')
            self.assertEqual(table.cell(1,1).text,'12.34\n-56.78\n0.00')
            table.cell(1,1).paragraphs[0].add_run(' edited')
            doc.save(root/'edited.docx')
            self.assertEqual(Document(root/'edited.docx').tables[0].cell(1,1).text,'12.34\n-56.78\n0.00 edited')

    def test_blank_record_keeps_later_value_on_its_source_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.pdf';output=root/'out.docx'
            commands=b''
            for y in (600,675,700):commands+=f'48 {y} m 330 {y} l S '.encode()
            for x in (48,190,330):commands+=f'{x} 600 m {x} 700 l S '.encode()
            commands+=text(55,680,'District')+text(200,680,'Amount')
            for y,label in [(660,'Alpha'),(640,'Beta'),(620,'Gamma')]:commands+=text(55,y,label)
            commands+=text(200,660,'10')+text(200,620,'30')
            fixture(source,content=commands);convert(source,output)
            table=Document(output).tables[0]
            self.assertEqual(table.cell(1,0).text,'Alpha\nBeta\nGamma')
            self.assertEqual(table.cell(1,1).text,'10\n\n30')

    def test_irregular_record_gaps_preserve_missing_middle_and_edge_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.pdf';output=root/'out.docx'
            commands=b''
            for y in (560,675,700):commands+=f'48 {y} m 500 {y} l S '.encode()
            for x in (48,190,330,500):commands+=f'{x} 560 m {x} 700 l S '.encode()
            commands+=text(55,680,'District')+text(200,680,'Middle missing')+text(340,680,'Edges missing')
            for y,label in [(660,'Alpha'),(640,'Beta'),(605,'Gamma'),(580,'Delta')]:commands+=text(55,y,label)
            for y,value in [(660,'10'),(605,'30'),(580,'40')]:commands+=text(200,y,value)
            for y,value in [(640,'20'),(605,'30')]:commands+=text(340,y,value)
            fixture(source,content=commands);convert(source,output)
            table=Document(output).tables[0]
            self.assertEqual(table.cell(1,0).text,'Alpha\nBeta\nGamma\nDelta')
            self.assertEqual(table.cell(1,1).text,'10\n\n30\n40')
            self.assertEqual(table.cell(1,2).text,'\n20\n30\n')

    def test_one_shared_baseline_does_not_infer_record_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.pdf';output=root/'out.docx'
            commands=b''
            for y in (600,675,700):commands+=f'48 {y} m 330 {y} l S '.encode()
            for x in (48,190,330):commands+=f'{x} 600 m {x} 700 l S '.encode()
            commands+=text(55,680,'Description')+text(200,680,'Value')
            for y,label in [(660,'First'),(640,'Second'),(620,'Third')]:commands+=text(55,y,label)
            commands+=text(200,660,'Single')
            fixture(source,content=commands);convert(source,output)
            self.assertEqual(Document(output).tables[0].cell(1,1).text,'Single')

    def test_horizontal_groups_remain_one_cell_line(self):
        blocks=words_to_blocks([word('Left',50,50,width=30),word('Right',150,50,width=30),
                               word('Next',50,70,width=30)],612,792,split_columns=False,merge_lines=False)
        self.assertEqual([b['text'] for b in blocks],['Left Right','Next'])
        self.assertEqual(''.join(r['text'] for r in blocks[0]['runs']),'Left Right')

    def test_heading_and_list_lines_in_cell_are_not_merged(self):
        words=[word('Title',50,50,width=60,size=24),word('Continued',50,79,width=60,size=24),
               word('1.',50,120,width=10),word('Item',68,120,width=40),word('Continuation',68,136,width=80)]
        blocks=words_to_blocks(words,612,792,split_columns=False,merge_lines=False)
        self.assertEqual([b['text'] for b in blocks],['Title','Continued','1. Item','Continuation'])


if __name__ == '__main__':
    unittest.main()
