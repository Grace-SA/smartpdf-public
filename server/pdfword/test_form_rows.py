import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from docx import Document
from PIL import Image
from columns import column_flow
from exporter import export_word
from form_rows import inline_rows
from layout import form_controls, graphics, words_to_blocks


class FormRowsTests(unittest.TestCase):
    def test_small_controls_remain_separate_including_unchecked_squares(self):
        rects = [dict(x0=30, x1=39, top=y, bottom=y+9, stroke=True, fill=False)
                 for y in (50, 62, 74, 86)]
        page = SimpleNamespace(rects=rects, images=[], curves=[], lines=[], width=612, height=792,
            extract_words=lambda: [dict(text="Choice",x0=42,x1=70,top=y,bottom=y+9) for y in (50,62,74,86)])
        self.assertEqual(len(form_controls(page)), 4)
        boxes = graphics(page, [])
        self.assertEqual(len(boxes), 4)
        self.assertTrue(all(b[3]-b[1] == 11 for b in boxes))
        self.assertEqual(form_controls(page, [dict(bbox=[20,40,50,100])]), [])
        self.assertEqual(form_controls(SimpleNamespace(rects=rects[:3])), [])

    def test_label_value_checkbox_export_in_same_paragraph_without_column_break(self):
        def text(identity, value, box):
            return dict(id=identity, kind='paragraph', text=value, bbox=box, static_form=True)
        blocks = [text('name','Name:',[30,50,60,61]), text('value','Example',[100,48,150,61]),
                  dict(id='check',kind='image',bbox=[180,50,191,61],asset='check.png',static_form=True),
                  text('yes','Yes',[195,50,213,61]), text('next','Next field',[30,70,100,81])]
        planned=inline_rows(column_flow(blocks,612))
        self.assertEqual([b['kind'] for b in planned],['form_row','paragraph'])
        self.assertEqual([b['id'] for b in planned[0]['items']],['name','value','check','yes'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); Image.new('RGB',(11,11),'white').save(root/'check.png')
            export_word(dict(schema=2,pages=[dict(index=0,width=612,height=792,blocks=blocks)]),root/'out.docx',root)
            doc=Document(root/'out.docx')
            self.assertEqual(doc.paragraphs[0].text, 'Name:\tExample\t\tYes')
            self.assertEqual(len(doc.inline_shapes),1)
            self.assertEqual(doc.paragraphs[1].text,'Next field')

    def test_unmarked_prose_and_overlapping_regions_are_not_combined(self):
        blocks=[dict(kind='paragraph',bbox=[30,50,80,62],text='A'),dict(kind='paragraph',bbox=[90,50,130,62],text='B')]
        self.assertIs(inline_rows(blocks),blocks)
        blocks[0]['static_form']=True
        blocks[1]['bbox']=[70,50,130,62]
        self.assertEqual(len(inline_rows(blocks)),2)

    def test_font_metrics_and_checkbox_gaps_do_not_reorder_fields(self):
        words = [dict(text=t,x0=x,x1=x+w,top=top,bottom=62,chars=[])
                 for t,x,w,top in [('Age:',30,20,53),('12',60,12,51),
                                   ('Gender:',110,35,53),('Option',165,35,53)]]
        blocks=words_to_blocks(words,612,792,merge_paragraphs=False,controls=[[150,51,161,62]])
        self.assertEqual([b['text'] for b in blocks],['Age: 12','Gender:','Option'])

    def test_two_underlines_export_in_form_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);Image.new('RGB',(100,3),'black').save(root/'line.png')
            blocks=[dict(id=str(i),kind='image',bbox=[x,50,x+100,53],asset='line.png',static_form=True)
                    for i,x in enumerate((30,180))]
            report=export_word(dict(schema=2,pages=[dict(index=0,width=612,height=792,blocks=blocks)]),root/'out.docx',root)
            self.assertEqual(report['images'],2)
            self.assertEqual(len(Document(root/'out.docx').inline_shapes),2)

    def test_unlabelled_chart_markers_are_not_form_controls(self):
        rects=[dict(x0=x,x1=x+9,top=50,bottom=59,stroke=True,fill=False) for x in (30,60,90,120)]
        page=SimpleNamespace(rects=rects,extract_words=lambda:[])
        self.assertEqual(form_controls(page),[])
