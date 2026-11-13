"""Boundary coverage for copied collision-tail normalization and atomic screening."""
import os,shutil
from contextlib import closing
import pytest
import pypdfium2 as pdfium
from smartppt import regional,word_clusters


def test_whole_components_only_and_unknown_assessment_rejects_all():
    groups=[(['one'],[{'index':1},{'index':2}]),(['two'],[{'index':3},{'index':4}])]
    assert regional._screen_complete_components(groups,[True,False,True,True])==groups[1:]
    assert regional._screen_complete_components(groups,[True,True,False,True])==groups[:1]
    for flags in (None,[],[True,True],[True]*5,[True,True,1,True],(True,)*4):
        assert regional._screen_complete_components(groups,flags)==[]

@pytest.mark.parametrize('kwargs',[{},dict(word_regions=True),dict(word_regions=True,word_clusters=True),
    dict(word_regions=True,word_clusters=True,cluster_mode='adjacent')])
def test_normalization_is_not_available_outside_collision_mode(kwargs):
    with pytest.raises(ValueError):regional.objects_for_page(None,normalize_tails=True,**kwargs)

@pytest.mark.parametrize('updates',[{},dict(extend=True,word_regions=True),
    dict(extend=True,word_regions=True,word_clusters=True,cluster_mode='collision'),
    dict(extend=True,word_regions=True,word_clusters=True,cluster_mode='collision',spacing_retry=True,alternative_font='base-sans')])
def test_normalization_is_never_unrestricted_or_replacement(updates):
    with pytest.raises(ValueError):regional._recover_regions(None,None,[1],None,normalize_tails=True,**updates)


def test_real_collision_graph_remains_intact_and_old_paths_unchanged(tmp_path):
    from reportlab.pdfgen import canvas
    source=tmp_path/'two-lines.pdf';c=canvas.Canvas(str(source),pagesize=(216,216))
    for y in (100,92):c._code.append(f'BT /F1 8 Tf 30 {y} Td [(Alpha) -400 (Beta)] TJ ET')
    c.save()
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page:
        original,_=regional.objects_for_page(page,word_regions=True,word_clusters=True,cluster_mode='collision')
        normalized,_=regional.objects_for_page(page,word_regions=True,word_clusters=True,cluster_mode='collision',normalize_tails=True)
        repeated,_=regional.objects_for_page(page,word_regions=True,word_clusters=True,cluster_mode='collision')
        assert [[r['text'] for r in runs] for _,runs in original]==[['Beta','Beta']]
        assert [[r['text'] for r in runs] for _,runs in repeated]==[['Beta','Beta']]
        assert [[r['text'] for r in runs] for _,runs in normalized]==[['Alpha','Alpha']]
        _,runs=normalized[0]
        assert all(r['generated_tail_space_trimmed'] for r in runs)
        assert word_clusters.source_verified(page,runs)
        # Both originally colliding lines stay in ONE indivisible component.
        assert runs[0]['baseline']!=runs[1]['baseline']


def test_resource_flagged_pages_skipped_in_new_normalized_stage(monkeypatch):
    from smartppt import regional_order,light_font
    previous={1:{'source_ranges':[[0,1]],'warnings':['word_cluster_resource_limit']},2:{'source_ranges':[[3,4]],'warnings':[]}}
    calls=[]
    def recover(source,target,pages,settings,**kwargs):
        calls.append((list(pages),kwargs));return previous if len(calls)==1 else {}
    monkeypatch.setattr(regional,'_recover_regions',recover)
    monkeypatch.setattr(regional_order,'restore_source_order',lambda *a:None)
    monkeypatch.setattr(light_font,'capability',lambda *a,**k:False)
    monkeypatch.setattr(regional.shutil,'which',lambda _: '/usr/bin/pdftoppm')
    result=regional.recover_regions(None,None,[1,2],None)
    normalized=[pages for pages,options in calls if options.get('normalize_tails')]
    assert normalized==[[2],[2]]
    assert result[1] is previous[1]


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='actual Office renderer required')
def test_generated_numeric_separators_independent_shapes_embedded_text_order(tmp_path):
    """Text-shape transport proof, NOT a claim of passing conversion gates."""
    from reportlab.pdfgen import canvas
    from pptx import Presentation
    from pptx.util import Pt
    from smartppt.layout import extract_native,add_text
    from smartppt import base_font
    from smartppt.font_embedding import bundled_payloads,embed_noto
    from smartppt.render_gate import render_presentations
    from smartppt.config import Settings
    from smartppt.quality import normalized,ordered_numeric_tokens
    source=tmp_path/'numbers.pdf';c=canvas.Canvas(str(source),pagesize=(216,216))
    c._code.append('BT /F1 10 Tf 30 100 Td [(123) -1200 (456) -1200 (1,234) -1200 (123)] TJ ET');c.save()
    prs=Presentation();prs.slide_width=prs.slide_height=Pt(216);slide=prs.slides.add_slide(prs.slide_layouts[6])
    with pdfium.PdfDocument(source) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
        reference=tp.get_text_range();runs,_,_=extract_native(page,split_words=True,partial_regions=True)
        assert [r['text'] for r in runs]==['123 ','456 ','1,234 ','123']
        trimmed=word_clusters.trim_generated_tails(page,runs)
        assert word_clusters.source_verified(page,trimmed)
        assert [r['text'] for r in trimmed]==['123','456','1,234','123']
        assert [r['index'] for r in trimmed]==[r['index'] for r in runs]
        for run in trimmed:
            l,b,r,t=run['box'];add_text(slide,run['text'],l,216-t,r-l+4,24,10,base_font.FAMILY)
    before=tmp_path/'before.pptx';after=tmp_path/'after.pptx';prs.save(before)
    assert len(slide.shapes)==4
    embed_noto(before,after,bundled_payloads(family=base_font.FAMILY),base_font.FAMILY)
    pdf=render_presentations([after],tmp_path,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))[0]
    with pdfium.PdfDocument(pdf) as doc,closing(doc[0]) as page,closing(page.get_textpage()) as tp:
        actual=tp.get_text_range()
        assert normalized(actual)==normalized(reference)
        assert ordered_numeric_tokens(actual)==ordered_numeric_tokens(reference)
        assert ordered_numeric_tokens(actual)==['123','456','1,234','123']
        assert all('SmartPDFBaseSans' in obj.get_font().get_base_name() for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT]))


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='actual Office renderer required')
def test_normalized_transaction_screen_rebuild_and_final_rollback(tmp_path,monkeypatch):
    """Controlled guard/candidate seam proves wiring, NOT visual acceptance."""
    from reportlab.pdfgen import canvas
    from pptx import Presentation
    from smartppt import light_visual_guard
    from smartppt.config import Settings
    from smartppt.pdf import inspect_pdf
    from smartppt.preserve import convert_preserve
    from smartppt.quality import ordered_numeric_tokens
    source=tmp_path/'collision.pdf';c=canvas.Canvas(str(source),pagesize=(200,200));c.setFont('Helvetica',14)
    c.drawString(40,140,'123');c.drawString(100,80,'OMITTED');c.drawString(40,128.5,'123')
    c.drawString(100,140,'456');c.drawString(100,128.5,'456');c.drawString(20,20,'Footer 999');c.save()
    target=tmp_path/'candidate.pptx';convert_preserve(source,target,inspect_pdf(source))
    settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']);original=regional.objects_for_page
    def footer(page,**kwargs):
        objects,warnings=original(page,**kwargs)
        return [obj for obj in objects if all(r['box'][3]<40 for r in obj[1])],warnings
    monkeypatch.setattr(regional,'objects_for_page',footer)
    prior=regional._recover_regions(source,target,[1],settings,word_regions=True)
    assert prior[1]['covered_source_glyphs']==9
    warning='inferred_terminal_spaces_omitted_from_separate_textboxes'
    prior[1]['warnings'].append(warning)
    before=target.read_bytes();old_xml=[s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:]]
    def controlled_candidates(page,**kwargs):
        # Actual complete, source-verified numeric collision components. Bypass
        # only the tail-specific candidate filter at this seam: genuine tail
        # detection/ownership is independently tested with real TJ PDFs above.
        kwargs.pop('normalize_tails',None)
        return original(page,**kwargs)
    monkeypatch.setattr(regional,'objects_for_page',controlled_candidates)
    kwargs=dict(word_regions=True,word_clusters=True,cluster_mode='collision',normalize_tails=True,
                minimum_coverage=prior,extend=True,spacing_retry=True,character_fit=True)
    cases=[(None,False),([True]*3,False),([True]*5,False),([True,True,1,True],False),
           ([True]*4,False),([False,True,True,True],True)]
    for flags,final_accept in cases:
        target.write_bytes(before);screens=[];verifications=[]
        def assess(*args,**options):
            screens.append(list(args[7]));assert len(args[7])==4
            return flags
        def verify(*args,**options):
            with pdfium.PdfDocument(args[4]) as doc,closing(doc[args[5]]) as page,closing(page.get_textpage()) as tp:
                text=tp.get_text_range()
            verifications.append((list(args[7]),text));return final_accept
        monkeypatch.setattr(light_visual_guard,'assess',assess)
        monkeypatch.setattr(light_visual_guard,'verify',verify)
        result=regional._recover_regions(source,target,[1],settings,**kwargs)
        assert len(screens)==1
        if not final_accept:
            assert result=={} and target.read_bytes()==before
            assert len(verifications)==(1 if flags==[True]*4 and all(type(x) is bool for x in flags) else 0)
        else:
            assert result[1]['covered_source_glyphs']==15 and result[1]['added_word_clusters']==1
            assert result[1]['retained_regions']==prior[1]
            assert result[1]['baseline_render']==prior[1]['baseline_render']
            assert result[1]['warnings'].count(warning)==1
            assert len(verifications)==1 and len(verifications[0][0])==2
            assert all(box[0]>=100 for box in verifications[0][0])
            # Private recovery keeps retained shapes first; the public wrapper
            # performs source-order restoration afterward. No rejected 123 survives.
            assert ordered_numeric_tokens(verifications[0][1])==['999','456','456']
            assert [s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:1+len(old_xml)]]==old_xml
