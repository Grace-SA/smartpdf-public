"""Closed native body spans retain their original record applicability."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server/pdf-to-excel'))
import pdfplumber
from reportlab.pdfgen import canvas
from convert import ruled_tables, write_workbook
from layout_body_rowspans import recover, closed_side
from types import SimpleNamespace
from openpyxl import load_workbook


class BodySpanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self, extra=False, missing_edge=False):
        file = self.root / 'source.pdf'
        c = canvas.Canvas(str(file), pagesize=(380, 300))
        for x in (20,100,180,260,340):
            c.line(x,110,x,270)
        for r in range(9):
            y=270-20*r
            c.line(20,y,260,y)
            if r not in (4,5) and not (missing_edge and r==6):
                c.line(260,y,340,y)
        c.setFont('Helvetica',8)
        for r in range(8):
            for col in range(4):
                if col==3 and 3<=r<6:
                    continue
                c.drawString(25+80*col,257-20*r,f'{col+1}{r}.00')
        c.drawString(280,178,'1.50%')
        c.drawString(280,168,'Partial')
        if extra:
            c.drawString(280,197,'OTHER')
        c.save()
        doc=pdfplumber.open(file);self.addCleanup(doc.close);page=doc.pages[0]
        native=ruled_tables(page)
        model=copy.deepcopy(native[0]);model['method']='layout'
        for cell in model['cells']:
            left=20+80*cell['c'];top=30+20*cell['r']
            box=(left,top,left+80*cell['cs'],top+20*cell['rs'])
            chars=[g for g in page.chars if g['text'].strip() and box[0]<=g['x0'] and g['x1']<=box[2] and box[1]<=g['top'] and g['bottom']<=box[3]]
            if chars:
                cell['sourceTextCandidate']=[min(g['x0'] for g in chars),min(g['top'] for g in chars),max(g['x1'] for g in chars),max(g['bottom'] for g in chars)]
            if cell['c']==3 and cell['r']==3:
                cell.update(r=4,rs=1,text='1.50% Partial')
        return model,native,page

    def test_real_grid_moves_existing_value_and_preserves_other_cells(self):
        model,native,page=self.fixture();before=copy.deepcopy(model)
        got=recover(model,native,page)
        target=next(c for c in got['cells'] if c['text']=='1.50% Partial')
        self.assertEqual((target['r'],target['rs']),(3,3))
        self.assertEqual(model,before)
        original=next(c for c in model['cells'] if c['text']=='1.50% Partial')
        self.assertEqual(target['sourceTextCandidate'],original['sourceTextCandidate'])
        self.assertEqual([c for c in got['cells'] if c is not target],[c for c in model['cells'] if c is not original])
        self.assertEqual(got['widths'],model['widths']);self.assertEqual(got['heights'],model['heights'])

    def test_conflicting_model_value_or_span_or_duplicate_stays_unchanged(self):
        for conflict in [dict(r=3,c=3,rs=1,cs=1,text='12.00'),dict(r=3,c=3,rs=2,cs=1,text=''),dict(r=3,c=3,rs=1,cs=1,text='1.50% Partial')]:
            model,native,page=self.fixture();model['cells'].append(conflict)
            self.assertEqual(recover(model,native,page),model)

    def test_explicit_empty_single_cells_are_consumed(self):
        model,native,page=self.fixture()
        model['cells'] += [dict(r=r,c=3,rs=1,cs=1,text='') for r in (3,5)]
        got=recover(model,native,page)
        self.assertEqual([(c['r'],c['rs']) for c in got['cells'] if c['c']==3 and 3<=c['r']<6],[(3,3)])

    def test_extra_native_text_and_missing_border_are_not_recovered(self):
        for options in ({'extra':True},{'missing_edge':True}):
            model,native,page=self.fixture(**options)
            self.assertEqual(recover(model,native,page),model)

    def test_ambiguous_grid_and_unclosed_grid_are_not_authority(self):
        model,native,page=self.fixture()
        self.assertEqual(recover(model,native+copy.deepcopy(native),page),model)
        native[0]['closedGrid']=False
        self.assertEqual(recover(model,native,page),model)

    def test_row_evidence_must_agree_and_have_two_columns(self):
        for altered in ('disagree','sparse'):
            model,native,page=self.fixture()
            for c in model['cells']:
                if c['r'] in (3,4) and c['c']==0 and altered=='disagree':
                    c['r']=7-c['r']
                if c['c'] in (0,1) and altered=='sparse':
                    c['text'] += ' unmatched'
            self.assertEqual(recover(model,native,page),model)

    def test_nonmatching_text_and_nonnative_rotation_are_not_repaired(self):
        model,native,page=self.fixture()
        for c in model['cells']:
            if c['text']=='1.50% Partial':c['text']='１.50% Partial'
        self.assertEqual(recover(model,native,page),model)
        model,native,page=self.fixture()
        with patch.object(page,'rotation',90):self.assertEqual(recover(model,native,page),model)

    def test_border_proof_cannot_use_curves_or_stacked_tolerances(self):
        line=lambda x0,x1,y,kind='line':dict(x0=x0,x1=x1,top=y,bottom=y,object_type=kind)
        self.assertFalse(closed_side([line(0,1,0),line(1,10,0,'curve_edge')],True,0,0,10))
        self.assertFalse(closed_side([line(0,1,2),line(1,10,3)],True,0,0,10))
        self.assertTrue(closed_side([line(0,10,1.5)],True,0,0,10))

    def test_other_model_owner_nan_glyph_and_obstacle_are_rejected(self):
        for kind in ('owner','nan','image','annotation','crop'):
            model,native,page=self.fixture()
            target=next(c for c in model['cells'] if c['text']=='1.50% Partial')
            if kind=='owner':
                model['cells'][0]['sourceTextCandidate']=target['sourceTextCandidate'][:]
            elif kind=='nan':
                glyph=next(g for g in page.chars if g['text']=='P')
                glyph['matrix']=(float('nan'),0,0,1,0,0)
            elif kind in ('image','annotation'):
                obstacle=dict(x0=280,x1=300,top=120,bottom=132)
                if kind=='image':page.objects['image']=[obstacle]
                else:
                    with patch.object(type(page),'annots',new_callable=PropertyMock,return_value=[obstacle]):
                        self.assertEqual(recover(model,native,page),model,kind)
                    continue
            else:
                page.cropbox=(20,30,335,190)
            self.assertEqual(recover(model,native,page),model,kind)

    def test_final_layout_adapter_and_workbook_keep_applicability(self):
        from docling.datamodel.base_models import ConversionStatus
        from layout_tables import extract_layout_tables
        model,native,page=self.fixture(); source=self.root/'source.pdf'; original=source.read_bytes()
        predicted=SimpleNamespace(data=SimpleNamespace(num_rows=8,num_cols=4),prov=[SimpleNamespace(page_no=1)],model_dump=lambda:{})
        converter=SimpleNamespace(convert=lambda *a,**kw:SimpleNamespace(status=ConversionStatus.SUCCESS,document=SimpleNamespace(tables=[predicted])))
        with patch('layout_dense.dense_grid',return_value=None), patch('layout_tables.converter_for',return_value=converter), patch('layout_tables.refine_predictions',return_value=[{}]), patch('layout_grid.has_vertical_headers',return_value=False), patch('layout_open.recover_open_grid',return_value=None), patch('layout_tables.adapt_table',return_value=model), patch('layout_tables.prefer_native',return_value=model):
            result=extract_layout_tables(source,[0],'unused',[page],ruled_tables)
        table=dict(result[0][0],page=1,index=1)
        out=self.root/'output.xlsx';write_workbook([table],out,'separate')
        book=load_workbook(out);self.addCleanup(book.close)
        self.assertIn('D4:D6',str(book.active.merged_cells))
        self.assertEqual(book.active['D4'].value,'1.50% Partial')
        self.assertEqual(source.read_bytes(),original)

    def test_native_grid_can_omit_two_model_header_tiers(self):
        model,native,page=self.fixture()
        model['heights']=[10,10]+model['heights']
        model['bbox'][1]-=20
        for c in model['cells']:c['r']+=2
        before=copy.deepcopy(model)
        got=recover(model,native,page)
        target=next(c for c in got['cells'] if c['text']=='1.50% Partial')
        self.assertEqual((target['r'],target['rs']),(5,3))
        for old,new in zip(before['cells'],got['cells']):
            self.assertEqual(old['text'],new['text'])
            if old['text']!='1.50% Partial':self.assertEqual(old,new)
        self.assertEqual(got['heights'],before['heights'])
        self.assertEqual(model,before)

    def test_resource_limit_is_noop(self):
        model,native,page=self.fixture()
        model['cells'] *= 100
        self.assertEqual(recover(model,native,page),model)


if __name__ == '__main__':
    unittest.main()
