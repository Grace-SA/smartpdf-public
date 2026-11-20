"""Synthetic filled-rule grids: nested ownership and editable rotated headings."""
import copy
import tempfile
import unittest
from pathlib import Path
import pdfplumber
from docx import Document
from docx.oxml.ns import qn
from test_worker import fixture
from ruled_tables import reconstruct, attach_row_labels, visible_spaces
from model import validate, content_text, Rejected
from exporter import export_word


def rules(xs, ys):
    return [f'{x-.4} {ys[0]} .8 {ys[-1]-ys[0]} re f' for x in xs] + [
        f'{xs[0]} {y-.4} {xs[-1]-xs[0]} .8 re f' for y in ys]


class RuledTablesTests(unittest.TestCase):
    def test_mixed_direction_cell_leaves_existing_route_available(self):
        commands=rules([100,180,260],[500,550,650,720])
        commands += ['BT /F1 9 Tf 0 1 -1 0 130 665 Tm (North) Tj ET',
                     'BT /F1 9 Tf 140 680 Td (Note) Tj ET']
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'mixed.pdf'
            fixture(source,'\n'.join(commands).encode())
            with pdfplumber.open(source) as pdf:
                page=pdf.pages[0]
                self.assertIsNone(reconstruct(page,page.extract_words(return_chars=True)))

    def test_overpainted_space_is_removed_but_word_separator_survives(self):
        chars=[dict(text=text,x0=x,x1=x+4,top=10,bottom=20)
               for text,x in [('A',10),(' ',11),(' ',14),('B',18)]]
        self.assertEqual(''.join(c['text'] for c in visible_spaces(chars)),'A B')

    def test_real_nested_grid_has_one_owner_and_editable_child(self):
        commands = rules([60,300,540], [480,600,720])
        commands += rules([80,140,200,260], [620,650,680,710])
        for r,y in enumerate([630,660,690]):
            for c,x in enumerate([90,150,210]):
                commands.append(f'BT /F1 8 Tf {x} {y} Td (V{r}{c}) Tj ET')
        commands.append('BT /F1 10 Tf 330 650 Td (Outer) Tj ET')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td);source=root/'grid.pdf';dest=root/'grid.docx'
            fixture(source, '\n'.join(commands).encode())
            with pdfplumber.open(source) as pdf:
                page=pdf.pages[0];tables=reconstruct(page,page.extract_words(return_chars=True))
            self.assertEqual(len(tables),1)
            children=[p for c in tables[0]['cells'] for p in c.get('content',[]) if p['kind']=='table']
            self.assertEqual(len(children),1)
            self.assertEqual((children[0]['rows'],children[0]['cols']),(3,3))
            tables[0]['id']='parent'
            model=dict(schema=2,pages=[dict(index=0,width=612,height=792,blocks=tables)])
            validate(model)
            self.assertEqual(content_text(tables[0]).count('V00'),1)
            export_word(model,dest,root)
            doc=Document(dest)
            self.assertEqual(len(doc.tables),1)
            nested=doc.element.body.findall('.//'+qn('w:tc')+'/'+qn('w:tbl'))
            self.assertEqual(len(nested),1)
            self.assertIn('V00',''.join(nested[0].itertext()))
            bad=copy.deepcopy(model)
            owner=next(c for c in bad['pages'][0]['blocks'][0]['cells'] if c.get('content'))
            owner['content'][0]['bbox']=[1,1,20,20]
            with self.assertRaisesRegex(Rejected,'outside its cell'):validate(bad)

    def test_rotated_heading_direction_and_empty_band_survive_export(self):
        commands=rules([100,180,260],[500,510,550,650,720])
        commands += ['BT /F1 9 Tf 0 1 -1 0 130 665 Tm (North Team) Tj ET',
                     'BT /F1 9 Tf 0 1 -1 0 210 665 Tm (South) Tj ET',
                     'BT /F1 9 Tf 110 580 Td (12) Tj ET']
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'rotated.pdf';dest=root/'rotated.docx'
            fixture(source,'\n'.join(commands).encode())
            with pdfplumber.open(source) as pdf:
                page=pdf.pages[0];tables=reconstruct(page,page.extract_words(return_chars=True))
            turns=[c for c in tables[0]['cells'] if c.get('direction')]
            self.assertEqual({c['text'] for c in turns},{'North Team','South'})
            self.assertTrue(all(c['direction']=='btLr' for c in turns))
            tables[0]['id']='rotated'
            model=dict(schema=2,pages=[dict(index=0,width=612,height=792,blocks=tables)])
            export_word(model,dest,root)
            doc=Document(dest)
            self.assertEqual(len(doc.element.body.findall('.//'+qn('w:textDirection'))),2)
            bad=copy.deepcopy(model);bad['pages'][0]['blocks'][0]['row_heights']=[float('nan')]*4
            with self.assertRaisesRegex(Rejected,'row heights'):validate(bad)

    def test_depth_limit_applies_before_text_traversal(self):
        block=dict(kind='paragraph',text='leaf')
        for _ in range(5):block=dict(kind='table',cells=[dict(text='',content=[block])])
        with self.assertRaises(Rejected):content_text(block)

    def test_row_labels_follow_y_intervals_not_text_order(self):
        from types import SimpleNamespace
        from test_aligned_tables import word
        table=dict(rows=4,cols=2,bbox=[100,100,200,180],widths=[50,50],cells=[
            dict(row=r,col=c,rowspan=1,colspan=1,text=str(r*2+c),
                 bbox=[100+50*c,100+20*r,150+50*c,120+20*r])
            for r in range(4) for c in range(2)])
        labels=[word('Row '+str(r),50,103+20*r) for r in reversed(range(4))]
        attach_row_labels([table],labels,SimpleNamespace(width=612,height=792))
        self.assertEqual(table['cols'],3)
        self.assertEqual({c['row']:c['text'] for c in table['cells'] if c['col']==0},
                         {r:'Row '+str(r) for r in range(4)})
