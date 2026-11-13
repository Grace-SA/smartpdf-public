"""Native font-family and wrapped-heading/list regression tests."""
import tempfile
import unittest
from pathlib import Path
from docx import Document
from exporter import plain_run, export_word
from fonts import font_family, SAFE_FAMILIES
from layout import words_to_blocks
from test_narrow_columns import word


def body():
    return [word('Body',50+i*40,200+j*20) for j in range(3) for i in range(5)]


class NativeTypographyTests(unittest.TestCase):
    def test_common_font_aliases_and_unknown_fallback(self):
        for name, expected in [('AAAAAA+TimesNewRomanPS-BoldMT','Times New Roman'),
                               ('aaaaaa+calibri','Calibri'),('Courier-BoldOblique','Courier New'),
                               ('HUMBXJ+Cambria-Bold','Cambria'),('UnknownCustomFont','Arial'),
                               ('../../font.ttf','Arial')]:
            self.assertEqual(font_family(name),expected)

    def test_font_family_survives_native_runs_and_docx_reopen(self):
        words = body()
        for w in words:
            w['chars'][0]['fontname']='CAAAAA+TimesNewRomanPSMT'
        blocks=words_to_blocks(words,612,792)
        self.assertTrue(all(r['font']=='Times New Roman' for b in blocks for r in b['runs']))
        doc=Document();p=doc.add_paragraph()
        for run in blocks[0]['runs']: plain_run(p,run['text'],run)
        plain_run(p,' unsafe',{'font':'arbitrary'})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'font.docx';doc.save(path);reopened=Document(path)
            self.assertEqual(reopened.paragraphs[0].runs[0].font.name,'Times New Roman')
            self.assertEqual(reopened.paragraphs[0].runs[-1].font.name,'Arial')

    def test_canonical_safe_names_are_idempotent(self):
        for name in SAFE_FAMILIES:
            self.assertEqual(font_family(name),name)

    def test_mixed_font_tie_uses_first_glyph_family(self):
        w=word('AB',50,50,width=24)
        w['chars']=[dict(size=12,fontname='Times-Roman'),dict(size=12,fontname='Courier')]
        blocks=words_to_blocks([w],612,792)
        self.assertEqual(blocks[0]['runs'][0]['font'],'Times New Roman')

    def test_wrapped_heading_is_one_paragraph_with_line_break(self):
        words=body()+[word('Long title',50,50,width=180,size=24),word('continued',50,79,width=70,size=24)]
        headings=[b for b in words_to_blocks(words,612,792) if b['kind']=='heading']
        self.assertEqual(len(headings),1)
        self.assertEqual(headings[0]['text'],'Long title\ncontinued')
        self.assertEqual(''.join(r['text'] for r in headings[0]['runs']),headings[0]['text'])

    def test_separated_headings_stay_distinct(self):
        words=body()+[word('First',50,50,size=24),word('Second',50,110,size=24)]
        self.assertEqual(sum(b['kind']=='heading' for b in words_to_blocks(words,612,792)),2)

    def test_list_continuation_and_ordinal_preserved(self):
        words=body()+[word('7.',50,50,width=10),word('Original',68,50,width=90),
                      word('continuation',68,66,width=90),word('9.',50,100,width=10),
                      word('Next',68,100,width=50)]
        blocks=words_to_blocks(words,612,792)
        lists=[b for b in blocks if b['kind']=='list']
        self.assertEqual([b['text'] for b in lists],['7. Original continuation','9. Next'])
        self.assertEqual(lists[0]['list_indent'],18)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i,b in enumerate(blocks):b['id']=f'b{i}';b['reading_order']=i
            export_word(dict(schema=2,pages=[dict(index=0,width=612,height=792,blocks=blocks)],warnings=[]),root/'out.docx',root)
            doc=Document(root/'out.docx');p=next(p for p in doc.paragraphs if p.text.startswith('7.'))
            self.assertEqual(p.text,'7. Original continuation')
            self.assertEqual(p.paragraph_format.left_indent.pt,18)
            self.assertEqual(p.paragraph_format.first_line_indent.pt,-18)

    def test_unindented_or_distant_prose_not_swallowed_by_list(self):
        for x,y in [(50,66),(68,100)]:
            words=body()+[word('7.',50,50,width=10),word('Original',68,50,width=90),word('Separate',x,y,width=90)]
            lists=[b for b in words_to_blocks(words,612,792) if b['kind']=='list']
            self.assertEqual(lists[0]['text'],'7. Original')


if __name__ == '__main__':
    unittest.main()
