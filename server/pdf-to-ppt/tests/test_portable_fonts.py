import hashlib
import os
import struct
import zipfile
from copy import deepcopy
from pathlib import Path
from lxml import etree as ET
import pytest
from pptx import Presentation
from pptx.util import Pt
from smartppt.config import ConversionError
from smartppt.font_embedding import noto_payload,embed_noto,P,R,REL,CT
from smartppt.layout import add_text
from smartppt.portable_fonts import script_segments,try_portable_fonts
from smartppt.quality import normalized,shape_text


def test_script_segments_preserve_text_and_complete_numbers():
    for text in ['项目预算：123.45元，合计678.90元。','年度 2026 报告','中文纯文本','Latin only 123.45','中文  English with spaces 中文']:
        chunks=script_segments(text)
        assert ''.join(chunks)==text
        if '123.45' in text:assert any('123.45' in c for c in chunks)
    assert script_segments('年度 2026 报告')==['年度 ','2026 ','报告']


def test_unknown_font_bytes_are_never_embedded():
    with pytest.raises(ConversionError,match='portable_font_integrity_failed'):
        noto_payload(b'not the approved public font')


def test_two_font_families_preserve_distinct_relationships(tmp_path):
    source=tmp_path/'source.pptx';one=tmp_path/'one.pptx';two=tmp_path/'two.pptx'
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    add_text(slide,'Sans 中文',20,20,200,30,18,'Noto Sans SC')
    add_text(slide,'Serif 中文',20,80,200,30,18,'Noto Serif SC');prs.save(source)
    embed_noto(source,one,{'regular':b'synthetic sans'})
    embed_noto(one,two,{'regular':b'synthetic serif','bold':b'synthetic bold serif'},'Noto Serif SC')
    with zipfile.ZipFile(two) as z:
        root=ET.fromstring(z.read('ppt/presentation.xml'));fonts=root.find('{'+P+'}embeddedFontLst')
        assert {f.find('{'+P+'}font').get('typeface') for f in fonts}=={'Noto Sans SC','Noto Serif SC'}
        rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('ppt/_rels/presentation.xml.rels'))}
        ids=[f.find('{'+P+'}'+style).get('{'+R+'}id') for f in fonts for style in ('regular','bold') if f.find('{'+P+'}'+style) is not None]
        assert len(ids)==len(set(ids))==3
        assert {z.read('ppt/'+rels[r]) for r in ids}=={b'synthetic sans',b'synthetic serif',b'synthetic bold serif'}


def test_font_package_relationships_and_unique_family(tmp_path):
    source=tmp_path/'before.pptx';target=tmp_path/'after.pptx';p=Presentation();s=p.slides.add_slide(p.slide_layouts[6])
    add_text(s,'中文 123',30,40,200,40,16,'Noto Sans SC');p.save(source)
    embed_noto(source,target,{'regular':b'synthetic-test-font','bold':b'synthetic-test-bold'})
    with zipfile.ZipFile(target) as z:
        root=ET.fromstring(z.read('ppt/presentation.xml'));fonts=root.find('{'+P+'}embeddedFontLst')
        assert len(fonts)==1 and fonts[0].find('{'+P+'}font').get('typeface')=='Noto Sans SC'
        assert root.get('embedTrueTypeFonts')=='1' and root.get('saveSubsetFonts')=='0'
        rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('ppt/_rels/presentation.xml.rels'))}
        types={t.get('PartName'):t.get('ContentType') for t in ET.fromstring(z.read('[Content_Types].xml'))}
        for style in ('regular','bold'):
            rid=fonts[0].find('{'+P+'}'+style).get('{'+R+'}id');name='ppt/'+rels[rid]
            assert name in z.namelist() and types['/'+name]=='application/x-fontdata'
    with pytest.raises(ConversionError,match='already_embedded'):
        embed_noto(target,tmp_path/'duplicate.pptx',{'regular':b'duplicate'})


def test_failed_optional_font_pass_preserves_package_and_metadata(tmp_path,settings,monkeypatch):
    import smartppt.portable_fonts as module
    path=tmp_path/'existing.pptx';path.write_bytes(b'untouched')
    def fail(source,target,report,settings):
        report['pages'][0]['route']='wrong'
        raise ConversionError('layout_render_failed')
    monkeypatch.setattr(module,'finalize_portable_fonts',fail)
    report={'pages':[{'page':1,'route':'native-coordinate'}]}
    try_portable_fonts(None,path,report,settings)
    assert path.read_bytes()==b'untouched' and report['pages'][0]['route']=='native-coordinate'
    assert report['font_portability']=={'embedded':False,'error':'layout_render_failed'}


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_small_scan_words_keep_numbers_and_do_not_require_cjk_font(tmp_path,settings,monkeypatch):
    from smartppt.render_gate import render_presentations
    import smartppt.portable_fonts as module
    def forbidden(*args):raise AssertionError('No CJK font is used')
    monkeypatch.setattr(module,'bundled_payloads',forbidden)
    target=tmp_path/'small.pptx';p=Presentation();p.slide_width=Pt(400);p.slide_height=Pt(400)
    s=p.slides.add_slide(p.slide_layouts[6]);add_text(s,'North 123.45 South 678.90',30,70,350,20,9);p.save(target)
    settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER'];source=render_presentations([target],tmp_path,settings)[0]
    report={'pages':[{'page':1,'route':'paddle-ocr'}]};try_portable_fonts(source,target,report,settings)
    assert report['font_portability']['validated'] and not report['font_portability']['embedded']
    texts=[s.text.strip() for s in Presentation(target).slides[0].shapes if s.has_text_frame]
    assert normalized(''.join(texts))=='North123.45South678.90'
    if report['font_portability']['positioned_small_text_pages']:
        assert texts==['North','123.45','South','678.90']
    else:
        # An already pixel-perfect source must remain unchanged if splitting
        # adds antialiasing error, even though all words have correct positions.
        assert report['font_portability']['script_layout_rejected_pages']==[1]
        assert texts==['North 123.45 South 678.90']


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER') or not os.getenv('SMARTPPT_CJK_FONT'),reason='real Office renderer and approved font required')
@pytest.mark.parametrize('family',['Noto Sans SC','Noto Serif SC'])
def test_actual_embedded_font_and_script_layout_are_verified(tmp_path,settings,monkeypatch,family):
    if family=='Noto Serif SC' and not os.getenv('SMARTPPT_CJK_SERIF_FONT'):pytest.skip('optional approved serif font required')
    from smartppt.render_gate import render_presentations
    import smartppt.portable_fonts as module
    target=tmp_path/'original.pptx';p=Presentation();p.slide_width=Pt(500);p.slide_height=Pt(400)
    s=p.slides.add_slide(p.slide_layouts[6]);add_text(s,'中文预算123.45元，年度2026。',30,50,420,30,18,family)
    add_text(s,'粗体合计678.90元',30,130,420,30,18,family,bold=True)
    add_text(s,'Footer 678.90',30,300,250,25,14);p.save(target)
    settings.renderer_path=os.environ['SMARTPPT_TEST_RENDERER'];rendered=render_presentations([target],tmp_path,settings)[0]
    report={'pages':[{'page':1,'route':'paddle-ocr','ink_targets':[{'shape':0,'bbox':[30,50,450,80]}]}]}
    expected=normalized(''.join(shape_text(s.shapes)))
    try_portable_fonts(rendered,target,report,settings)
    assert report['font_portability']['embedded'],report
    assert report['font_portability']['faces']==['regular','bold']
    assert report['font_portability']['families']=={family:['regular','bold']}
    assert report['font_portability']['positioned_script_pages']==[1]
    result=Presentation(target);slide=result.slides[0]
    assert normalized(''.join(shape_text(slide.shapes)))==expected
    assert len({s.shape_id for s in slide.shapes})==len(slide.shapes)
    assert 'ink_targets' not in report['pages'][0] and 'ink_targets_before_font_portability' in report['pages'][0]
    with zipfile.ZipFile(target) as z:
        assert len([n for n in z.namelist() if n.endswith('.fntdata')])==2
        data=z.read(next(n for n in z.namelist() if n.endswith('.fntdata')))
        size,font_size,version,flags=struct.unpack_from('<IIII',data)
        assert size==len(data) and font_size>1000000 and version==0x20001 and flags==0
        assert struct.unpack_from('<H',data,34)[0]==0x504c
        from io import BytesIO
        from fontTools.ttLib import TTFont
        with TTFont(BytesIO(data[-font_size:])) as font:
            assert 'PREAMBLE' in font['name'].getDebugName(13)
            assert 'Adobe' in font['name'].getDebugName(13)
            assert font.getBestCmap()[0x957f]!=font.getBestCmap()[0x2ed3]
            assert 'fvar' not in font
    # A rerun must neither duplicate font records nor shift shape indices again.
    before=hashlib.sha256(target.read_bytes()).hexdigest();metadata=deepcopy(report)
    try_portable_fonts(rendered,target,report,settings)
    assert report==metadata and hashlib.sha256(target.read_bytes()).hexdigest()==before
    # Failure after font packaging still leaves the caller's original file intact.
    reject=tmp_path/'reject.pptx';p.save(reject);before=reject.read_bytes()
    monkeypatch.setattr(module,'accept_candidate',lambda *_:False)
    failed={'pages':[{'page':1,'route':'native-coordinate'}]}
    try_portable_fonts(rendered,reject,failed,settings)
    assert reject.read_bytes()==before and failed['font_portability']['error']=='portable_font_visual_rejected'
