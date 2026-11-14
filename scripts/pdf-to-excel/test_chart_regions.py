import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from layout_chart_regions import partitions, verify_fields, context, recover
from layout_tables import LayoutError
from convert import write_workbook
from openpyxl import load_workbook


class ChartRegionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def fixture(self, series=True, invisible=None, extra=False, frames=1):
        path=self.root/'source.pdf';height=600 if frames==1 else 1200
        c=canvas.Canvas(str(path),pagesize=(800,height))
        for bottom in ([60] if frames==1 else [60,650]):
            top=bottom+490
            for x in (20,540,780):c.line(x,bottom,x,top)
            for y in (bottom,bottom+120,bottom+240,bottom+360,top):c.line(20,y,540,y)
            count=3 if frames==1 else 2
            ph=490/count
            for i in range(count+1):c.line(540,bottom+i*ph,780,bottom+i*ph)
            c.setFont('Helvetica',10)
            for i in range(12):
                for x,value in ((25,f'Record{i}'),(200,f'{i+10}.25'),(300,f'{i+20}.50'),(420,f'{i+30}.75')):
                    c.drawString(x,top-20-i*35,value)
            for n in range(count):
                base=bottom+n*ph
                c.setFont('Helvetica',8);c.drawString(620,base+ph-15,'Energy trend')
                c.setFont('Helvetica',6)
                for i in range(7):
                    y=base+40+i*(ph-75)/6
                    c.line(580,y,760,y);c.drawRightString(570,y-2,str(i*10))
                c.line(580,base+40,580,base+ph-35);c.line(760,base+40,760,base+ph-35)
                c.setFont('Helvetica',5)
                for i,letter in enumerate('JFMAMJJASOND'):c.drawString(583+i*14,base+32,letter)
                c.setFont('Helvetica',6)
                for x,label in ((625,'2023'),(715,'2024')):
                    c.line(x-30,base+15,x-5,base+15);c.drawString(x,base+12,label)
                if series:
                    c.saveState()
                    if invisible=='white':c.setStrokeColorRGB(1,1,1)
                    if invisible in ('transparent','transparent-grid-vertices'):c.setStrokeAlpha(0)
                    for delta in (0,20):
                        p=c.beginPath()
                        ypoint=lambda i: (base+40+(i%3+delta/20)*(ph-75)/6
                                          if invisible=='transparent-grid-vertices' else base+65+delta+(i%3)*8)
                        p.moveTo(585,ypoint(0))
                        for i in range(1,16):p.lineTo(585+i*11,ypoint(i))
                        c.drawPath(p)
                    c.restoreState()
                    if invisible in ('covered','black-covered'):
                        c.setFillColorRGB(*((0,0,0) if invisible=='black-covered' else (1,1,1)));c.rect(581,base+55,177,65,stroke=0,fill=1);c.setFillColorRGB(0,0,0)
                if extra:
                    c.setFont('Helvetica',6)
                    for row,values in enumerate((('Summary','12','21'),('Another','34','43'))):
                        for x,value in zip((610,660,710),values):
                            c.drawString(x,base+115-row*10,value)
        c.save();return path

    def source(self):
        pdf=pdfplumber.open(self.fixture());self.addCleanup(pdf.close);page=pdf.pages[0]
        old=[dict(bbox=[20,50,780,540])]
        candidates=partitions(page,old);self.assertEqual(len(candidates),1)
        region,panels,frame=candidates[0];words=page.extract_words(x_tolerance=2,y_tolerance=3)
        selected=[w for w in words if w['x1']<540]
        ys=sorted(set(round(w['top'],2) for w in selected));cells=[]
        for w in selected:
            cells.append(dict(r=ys.index(round(w['top'],2)),c=(0 if w['x0']<100 else 1 if w['x0']<250 else 2 if w['x0']<350 else 3),rs=1,cs=1,text=w['text'],sourceTextCandidate=[w['x0'],w['top'],w['x1'],w['bottom']]))
        table=dict(bbox=region,widths=[160,100,120,140],heights=[35]*12,cells=cells,method='layout-region')
        old[0]['cells']=[dict(text=w['text'],sourceTextCandidate=[w['x0'],w['top'],w['x1'],w['bottom']]) for w in words]
        return page,old,region,panels,words,table

    def test_complete_fields_and_source_context_survive_workbook(self):
        page,old,region,panels,words,table=self.source()
        self.assertTrue(verify_fields(table,words,region))
        with patch('layout_chart_regions.recover_regions',return_value=([table],1)):
            tables,used=recover(self.root/'source.pdf',0,page,old,None,2)
        self.assertEqual(used,1);t=tables[0];t.update(page=1,index=1)
        t['sourceContext']='Existing context must survive'
        out=self.root/'out.xlsx';write_workbook(tables,out,'tables');ws=load_workbook(out).active
        self.assertEqual(ws['B1'].value,'10.25')
        self.assertIn('Existing context must survive',ws['A1'].comment.text)
        self.assertIn('Chart region 1',ws['A1'].comment.text)
        self.assertIn('not interpreted as table data',ws['A1'].comment.text)
        for token in ('Energy','trend','2023','2024'):self.assertEqual(t['chartSourceContext'].splitlines().count(token),3)

    def test_swaps_same_character_bag_and_numeric_reversal_fail(self):
        page,old,region,panels,words,table=self.source()
        for mode in ('row','col','number'):
            t=copy.deepcopy(table)
            if mode=='number':t['cells'][1]['text']='52.01'
            elif mode=='row':
                for c in t['cells']:
                    if c['r'] in (0,1):c['r']=1-c['r']
            else:
                for c in t['cells']:
                    if c['c'] in (1,2):c['c']=3-c['c']
            self.assertFalse(verify_fields(t,words,region),mode)

    def test_one_record_shifted_a_column_cannot_pass_string_conservation(self):
        _,_,region,_,words,table=self.source()
        table['widths'].append(50)
        for cell in table['cells']:
            if cell['r']==5 and cell['c']>=1:
                cell['c']+=1
        self.assertFalse(verify_fields(table,words,region))

    def test_missing_duplicate_or_crossing_source_tokens_fail(self):
        page,old,region,panels,words,table=self.source()
        t=copy.deepcopy(table);t['cells'].pop();self.assertFalse(verify_fields(t,words,region))
        t=copy.deepcopy(table);t['cells'].append(copy.deepcopy(t['cells'][0]));self.assertFalse(verify_fields(t,words,region))
        changed=copy.deepcopy(words);changed[0]['x0']=region[0]-1
        self.assertFalse(verify_fields(table,changed,region))

    def test_no_series_does_not_remove_an_adjacent_data_column(self):
        with pdfplumber.open(self.fixture(series=False)) as pdf:
            self.assertEqual(partitions(pdf.pages[0],[dict(bbox=[20,50,780,540])]),[])

    def test_failed_field_proof_and_budget_refuse_instead_of_returning_pollution(self):
        page,old,region,panels,words,table=self.source()
        with self.assertRaises(LayoutError):recover(self.root/'source.pdf',0,page,old,None,0)
        table['cells'][0]['text']='Changed'
        with patch('layout_chart_regions.recover_regions',return_value=([table],1)),self.assertRaises(LayoutError):
            recover(self.root/'source.pdf',0,page,old,None,2)

    def test_actual_white_transparent_and_covered_curves_cannot_prove_charts(self):
        for kind in ('white','transparent','covered','black-covered','transparent-grid-vertices'):
            with self.subTest(kind=kind),pdfplumber.open(self.fixture(invisible=kind)) as pdf:
                with self.assertRaisesRegex(LayoutError,'visibility'):
                    partitions(pdf.pages[0],[dict(bbox=[20,50,780,540])])

    def test_borderless_numeric_summary_inside_plot_is_not_demoted_to_context(self):
        with pdfplumber.open(self.fixture(extra=True)) as pdf:
            with self.assertRaisesRegex(LayoutError,'unclassified'):
                partitions(pdf.pages[0],[dict(bbox=[20,50,780,540])])

    def test_two_real_source_frames_are_not_resolved_by_picking_first(self):
        with pdfplumber.open(self.fixture(frames=2)) as pdf:
            with self.assertRaisesRegex(LayoutError,'More than one'):
                partitions(pdf.pages[0],[dict(bbox=[20,60,780,1140])])

    def test_original_cross_region_or_unassigned_model_field_blocks_replacement(self):
        page,old,region,panels,words,table=self.source()
        for bounds in ([20,50,780,540],[0,0,10,10]):
            bad=copy.deepcopy(old)
            bad[0]['cells'].append(dict(text='Unproved',sourceTextCandidate=bounds))
            with self.subTest(bounds=bounds),patch('layout_chart_regions.recover_regions') as crop:
                with self.assertRaisesRegex(LayoutError,'cross or escape'):
                    recover(self.root/'source.pdf',0,page,bad,None,2)
                crop.assert_not_called()

    def test_context_never_silently_truncates(self):
        _,_,region,panels,words,_=self.source()
        words.append(dict(text='x'*16001,x0=550,x1=560,top=60,bottom=70))
        with self.assertRaises(LayoutError):context(words,region,panels)


if __name__=='__main__':unittest.main()
