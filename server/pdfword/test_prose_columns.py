import unittest
from prose_columns import narrow_prose_cuts
from layout import words_to_blocks
from columns import column_flow


class ProseColumnTests(unittest.TestCase):
    def words(self,prose=True):
        return [dict(text='A complete sentence finishes.' if prose else 'Aligned entry value',
                     x0=x,x1=x+168,top=130+row*10,bottom=138+row*10,chars=[])
                for row in range(60) for x in (45,222,399)]

    def test_narrow_gutters_require_prose_in_each_column(self):
        self.assertEqual(narrow_prose_cuts(self.words(),612,792),[217.5,394.5])
        self.assertEqual(narrow_prose_cuts(self.words(False),612,792),[])
        self.assertEqual(narrow_prose_cuts(self.words()[:90],612,792),[])

    def test_lines_are_not_joined_across_a_proven_narrow_gutter(self):
        words=[dict(text=t,x0=x,x1=x+168,top=100,bottom=110,chars=[])
               for x,t in [(45,'Left'),(222,'Middle'),(399,'Right')]]
        blocks=words_to_blocks(words,612,792,column_cuts=[217,394])
        self.assertEqual([b['text'] for b in blocks],['Left','Middle','Right'])

    def test_header_and_page_label_do_not_disable_proven_body_columns(self):
        blocks=[dict(id='header',kind='paragraph',text='Synthetic publication heading',bbox=[120,34,490,44],native_columns=[217,394]),
                dict(id='number',kind='paragraph',text='100',bbox=[536,34,566,44],native_columns=[217,394]),
                dict(id='rule',kind='image',bbox=[44,47,568,53],native_columns=[217,394])]
        for col,x in enumerate((45,222,399)):
            for row in range(2):
                blocks.append(dict(id=f'{col}-{row}',kind='paragraph',text=f'Column {col} paragraph {row}',bbox=[x,60+row*30,x+168,80+row*30],native_columns=[217,394]))
        flow=column_flow(blocks,612)
        self.assertEqual(flow[0]['kind'],'form_row')
        self.assertEqual([b['id'] for b in flow[0]['items']],['header','number'])
        self.assertEqual(sum(b['kind']=='columns_start' for b in flow),1)
        self.assertEqual([b['id'] for b in flow if 'id' in b],['rule','0-0','0-1','1-0','1-1','2-0','2-1'])

    def test_pdf_font_descriptors_keep_serif_family_for_narrow_prose(self):
        from types import SimpleNamespace
        from pdfminer.psparser import PSLiteral
        from prose_columns import native_font_families
        from layout import font_family
        fonts={'F1':{'BaseFont':PSLiteral('SyntheticSerif'),'FontDescriptor':{'Flags':34}},
               'F2':{'BaseFont':PSLiteral('SyntheticMono'),'FontDescriptor':{'Flags':1}}}
        families=native_font_families(SimpleNamespace(page_obj=SimpleNamespace(resources={'Font':fonts})))
        self.assertEqual(font_family(['syntheticserif'],families),'Times New Roman')
        self.assertEqual(font_family(['syntheticmono'],families),'Courier New')
        self.assertEqual(font_family(['unknown'],families),'Arial')

    def test_symbol_font_bullet_stays_with_its_text(self):
        words=[dict(text='•',x0=231,x1=235,top=120,bottom=129,chars=[]),
               dict(text='First item',x0=240,x1=290,top=122.27,bottom=131.27,chars=[])]
        self.assertEqual([b['text'] for b in words_to_blocks(words,612,792,column_cuts=[217,394])],['• First item'])

    def test_other_column_font_metrics_do_not_detach_a_bullet(self):
        words=[dict(text='Neighbour',x0=45,x1=200,top=158.4,bottom=167.4,chars=[]),
               dict(text='•',x0=231,x1=235,top=159.4,bottom=168.4,chars=[]),
               dict(text='Item',x0=240,x1=280,top=161.66,bottom=170.66,chars=[])]
        self.assertEqual([b['text'] for b in words_to_blocks(words,612,792,column_cuts=[217,394])],['Neighbour','• Item'])
