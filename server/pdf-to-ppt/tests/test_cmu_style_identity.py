"""Real Office style selection must agree with the approved CMU face bytes."""
import os
from contextlib import closing
import pytest
import pypdfium2 as pdfium
from pptx import Presentation
from smartppt.layout import add_text
from smartppt.font_embedding import bundled_payloads, embed_noto
from smartppt.render_gate import render_presentations
from smartppt.config import Settings

STYLES = [('regular',False,False,'Regular'),('bold',True,False,'Bold'),
          ('italic',False,True,'Italic'),('boldItalic',True,True,'BoldItalic')]
FAMILY = 'CMU Typewriter Text'

@pytest.mark.parametrize('style,bold,italic,suffix',STYLES)
def test_typewriter_pitch_matches_approved_face(style,bold,italic,suffix):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    shape=add_text(slide,'Review 123.45',30,30,300,40,18,FAMILY,bold=bold,italic=italic)
    props=shape.text_frame.paragraphs[0].runs[0]._r.get_or_add_rPr()
    latin=props.find('{http://schemas.openxmlformats.org/drawingml/2006/main}latin')
    assert latin.get('pitchFamily')==('50' if bold else '49')
    assert props.get('b')==('1' if bold else '0')
    assert props.get('i')==('1' if italic else '0')

@pytest.mark.parametrize('family',['CMU Serif','CMU Sans Serif','Arial','CMU Typewriter Text Variable Width','CMU Typewriter Text Unknown'])
def test_pitch_change_is_exact_family_only(family):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    shape=add_text(slide,'Review',30,30,300,40,18,family)
    props=shape.text_frame.paragraphs[0].runs[0]._r.get_or_add_rPr()
    assert all(node.get('pitchFamily') is None for node in props)

@pytest.mark.skipif(not (os.getenv('SMARTPPT_TEST_RENDERER') and os.getenv('SMARTPPT_CMU_FONT_DIR')),
                    reason='real Office renderer and approved CMU inputs required')
def test_four_typewriter_styles_actual_font_identity_before_and_after_embedding(tmp_path):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    lines=[]
    for i,(style,bold,italic,suffix) in enumerate(STYLES):
        text=f'Face{i} {style} 123.45 noam@example.com';lines.append(text)
        add_text(slide,text,30,30+i*60,600,40,18,FAMILY,bold=bold,italic=italic)
    before=tmp_path/'before.pptx';after=tmp_path/'after.pptx';prs.save(before)
    embed_noto(before,after,bundled_payloads(family=FAMILY,styles={s[0] for s in STYLES}),FAMILY)
    rendered=render_presentations([before,after],tmp_path,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))
    for file in rendered:
        with pdfium.PdfDocument(file) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
            raw=''.join(chr(pdfium.raw.FPDFText_GetUnicode(tp,i)) for i in range(tp.count_chars()))
            for text,(_,_,_,suffix) in zip(lines,STYLES):
                assert raw.count(text)==1,raw
                start=raw.index(text)
                # Check every visible character, not merely whether a correct
                # font happens to be embedded elsewhere in the document.
                for i,c in enumerate(text,start):
                    if c.isspace():continue
                    obj=tp.get_textobj(i);assert obj is not None
                    name=obj.get_font().get_base_name()
                    assert name.split('+')[-1]=='CMUTypewriter-'+suffix,(file,text,c,name)
