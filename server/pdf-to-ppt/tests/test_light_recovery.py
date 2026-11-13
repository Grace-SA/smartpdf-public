"""A regular Light substitute can add verified words, never replace them."""
import os,shutil
from copy import deepcopy
import pytest
from smartppt import regional, light_font
from smartppt.config import ConversionError


def run(**updates):
    r=dict(text='hello@example.com',source_base_font='SFTT1000',font='CMU Typewriter Text',bold=False,italic=False,rotation=0)
    r.update(updates);return r


@pytest.mark.parametrize('name',['SFTT1000','ABCDEF+SFTT1000','CMtt10','CMU Typewriter Text','CMU Typewriter Text-Regular'])
def test_exact_regular_typewriter_source_eligible(monkeypatch,name):
    monkeypatch.setattr(light_font,'approved_cmap',lambda:set(range(128)))
    original=run(source_base_font=name);before=deepcopy(original)
    selected=regional.alternative_cmu_light([('object',[original])])
    assert selected[0][1][0]['font']==light_font.FAMILY
    assert selected[0][1][0]['substituted'] and original==before


@pytest.mark.parametrize('updates',[{'source_base_font':'SFST1000'},{'source_base_font':'SFIT1000'},
    {'source_base_font':'SFTT1000Fake'},{'source_base_font':'CMtt10-Italic'},
    {'source_base_font':'Arial'},{'source_base_font':'ABCDE+SFTT1000'},
    {'source_base_font':'CMU Typewriter Text Light'},{'font':'Courier New'},
    {'bold':True},{'italic':True},{'rotation':90},{'text':'   '}])
def test_unsupported_source_or_style_stays_graphic(monkeypatch,updates):
    monkeypatch.setattr(light_font,'approved_cmap',lambda:set(range(128)))
    assert regional.alternative_cmu_light([('object',[run(**updates)])])==[]


def test_optional_or_unicode_refusal_does_not_mutate_input(monkeypatch):
    monkeypatch.setattr(light_font,'approved_cmap',lambda:set())
    original=[('object',[run()])];before=deepcopy(original)
    assert regional.alternative_cmu_light(original)==[] and original==before


@pytest.mark.parametrize('kwargs',[{},dict(extend=True,word_regions=True),dict(spacing_retry=True,word_regions=True)])
def test_light_substitute_is_never_replacement(kwargs):
    with pytest.raises(ValueError):regional._recover_regions(None,None,[1],None,alternative_font='cmu-light',**kwargs)


def test_optional_failure_stops_two_pass_loop_and_preserves_prior(monkeypatch):
    from smartppt import regional_order
    monkeypatch.setattr(light_font,'capability',lambda *a,**k:True)
    previous={'source_ranges':[[0,5]],'warnings':[]};calls=[]
    def recover(*args,**kwargs):
        calls.append(kwargs)
        if kwargs.get('alternative_font')=='cmu-light':raise ConversionError('portable_light_integrity_failed')
        return {1:previous} if len(calls)==1 else {}
    monkeypatch.setattr(regional,'_recover_regions',recover)
    monkeypatch.setattr(regional_order,'restore_source_order',lambda *a:None)
    assert regional.recover_regions(None,None,[1],None)[1] is previous
    assert previous['warnings']==['additional_cmu_light_extension_unavailable']
    assert sum(x.get('alternative_font')=='cmu-light' for x in calls)==1

@pytest.mark.skipif(not (os.getenv('SMARTPPT_TEST_RENDERER') and os.getenv('SMARTPPT_CMU_FONT_DIR') and shutil.which('pdftoppm') and os.name=='posix'),reason='pinned font, renderer and bounded Poppler required')
@pytest.mark.parametrize('character_fit',[True,False])
@pytest.mark.parametrize('page_size',[400,432])
def test_real_additive_light_retains_prior_and_embedded_render(tmp_path,monkeypatch,character_fit,page_size):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from pathlib import Path
    from pptx import Presentation
    from smartppt.config import Settings
    from smartppt.pdf import inspect_pdf
    from smartppt.preserve import convert_preserve
    from smartppt.font_embedding import bundled_payloads,embed_noto
    from smartppt.render_gate import render_presentations,metric
    from smartppt.quality import shape_text,normalized
    pdfmetrics.registerFont(TTFont('SyntheticLight',str(Path(os.environ['SMARTPPT_CMU_FONT_DIR'])/'cmunbtl.ttf')))
    source=tmp_path/'source.pdf';c=canvas.Canvas(str(source),pagesize=(page_size,page_size))
    c.setFont('SyntheticLight',14);c.drawString(30,310,'hello@example.com')
    c.setFont('Helvetica',14);c.drawString(30,50,'Footer 999');c.save()
    target=tmp_path/'candidate.pptx';convert_preserve(source,target,inspect_pdf(source))
    settings=Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']);original=regional.objects_for_page
    def footer(page,**kwargs):
        objects,warnings=original(page,**kwargs)
        return [o for o in objects if all(r['box'][3]<100 for r in o[1])],warnings
    monkeypatch.setattr(regional,'objects_for_page',footer)
    prior=regional._recover_regions(source,target,[1],settings,word_regions=True)
    assert prior[1]['covered_source_glyphs']==9
    def candidates(page,**kwargs):
        objects,warnings=original(page,**kwargs)
        for _,runs in objects:
            for r in runs:
                if '@' in r['text']:r.update(source_base_font='SFTT1000',font='CMU Typewriter Text')
        return objects,warnings
    monkeypatch.setattr(regional,'objects_for_page',candidates)
    before=target.read_bytes();xml=[s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:]]
    result=regional._recover_regions(source,target,[1],settings,word_regions=True,minimum_coverage=prior,extend=True,spacing_retry=True,character_fit=character_fit,alternative_font='cmu-light')
    if page_size==400:
        # This real LO runtime emits 399.9968567pt for a 400pt square.
        # Keep the original fixture as a strict geometry-uncertainty refusal;
        # do not mock the guard or change its dimension tolerance to admit it.
        assert result=={} and target.read_bytes()==before
        return
    # A 6-inch square remains exactly 432pt across both engines, so this
    # fixture exercises successful original gates AND the real four-DPI guard.
    assert result[1]['covered_source_glyphs']==26
    assert result[1]['retained_regions']==prior[1]
    assert result[1]['baseline_render']==prior[1]['baseline_render']
    assert result[1]['calibration_font']==light_font.FAMILY
    assert result[1]['extension_font_strategy']=='cmu-light-substitute'
    assert [s._element.xml for s in list(Presentation(target).slides[0].shapes)[1:1+len(xml)]]==xml
    embedded=tmp_path/'embedded.pptx';embed_noto(target,embedded,bundled_payloads(family=light_font.FAMILY),light_font.FAMILY)
    folder=tmp_path/'render';folder.mkdir();a,b=render_presentations([target,embedded],folder,settings)
    assert metric(a,b,0)=={'mae':0.0,'foreground_mae':0.0}
    assert normalized(''.join(shape_text(Presentation(embedded).slides[0].shapes))).count('hello@example.com')==1
    # No-op retry retains the accepted package byte-for-byte.
    current=target.read_bytes()
    assert regional._recover_regions(source,target,[1],settings,word_regions=True,minimum_coverage=result,extend=True,spacing_retry=True,character_fit=character_fit,alternative_font='cmu-light')=={}
    assert target.read_bytes()==current and current!=before
    # A changed retained pixel must reject the whole additive transaction.
    target.write_bytes(before)
    monkeypatch.setattr(regional,'retained_pixels_unchanged',lambda *_:False)
    assert regional._recover_regions(source,target,[1],settings,word_regions=True,minimum_coverage=prior,extend=True,spacing_retry=True,character_fit=character_fit,alternative_font='cmu-light')=={}
    assert target.read_bytes()==before


def test_font_integrity_is_checked_once_per_candidate_pass(monkeypatch):
    calls=[]
    def cmap():calls.append(1);return set(range(128))
    monkeypatch.setattr(light_font,'approved_cmap',cmap)
    assert len(regional.alternative_cmu_light([(i,[run()]) for i in range(1000)]))==1000
    assert calls==[1]


def test_both_raw_and_normalized_unicode_are_required(monkeypatch):
    monkeypatch.setattr(light_font,'approved_cmap',lambda:{ord('①')})
    assert regional.alternative_cmu_light([('object',[run(text='①')])])==[]


def test_expired_shared_light_budget_does_not_start_rendering(monkeypatch):
    monkeypatch.setattr(regional.time,'monotonic',lambda:20)
    assert regional._recover_regions(None,None,[1],None,word_regions=True,extend=True,spacing_retry=True,alternative_font='cmu-light',light_guard_deadline=19)=={}


@pytest.mark.parametrize('kwargs',[dict(light_shift=.2,alternative_font='cmu-light'),dict(light_shift=.1,alternative_font='base-sans')])
def test_shift_trial_scope_is_bounded(kwargs):
    with pytest.raises(ValueError):regional._recover_regions(None,None,[1],None,word_regions=True,extend=True,spacing_retry=True,**kwargs)
