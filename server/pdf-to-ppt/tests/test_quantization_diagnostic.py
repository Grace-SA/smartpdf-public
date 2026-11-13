"""Offline geometry proof cannot authorize production conversion."""
import importlib.util,json,os,sys,zipfile
from pathlib import Path
import pytest


def module():
    path=Path(__file__).parents[1]/'tools/public-native-quantization.py'
    spec=importlib.util.spec_from_file_location('canvas_diagnostic',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def pptx(path,xml):
    with zipfile.ZipFile(path,'w') as z:z.writestr('ppt/presentation.xml',xml)


def pdf(path):
    from reportlab.pdfgen import canvas
    c=canvas.Canvas(str(path),pagesize=(400,400));c.setFillColorRGB(0,0,0);c.rect(50,100,40,15,fill=1,stroke=0);c.save()


def test_raw_metadata_uses_decimal_strings_and_actual_emu(tmp_path):
    m=module();source=tmp_path/'s.pdf';pdf(source);deck=tmp_path/'x.pptx'
    pptx(deck,'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldSz cx="5080000" cy="5080000"/></p:presentation>')
    data=m.raw_metadata([source]*3,deck,0,tmp_path,m.guard.Deadline(10))
    assert data['emu']==[5080000,5080000]
    assert data['pages'][0]['media_box']==['0','0','400','400']
    assert data['pages'][0]['user_unit']=='1'

@pytest.mark.parametrize('xml',[
    '<!DOCTYPE p [<!ENTITY x "5080000">]><p>&x;</p>',
    '<!DOCTYPE p [<!ENTITY x "5080000">]><p>&x;</p>'.encode('utf-16'),
    '<presentation/>',
    '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldSz cx="nan" cy="400"/></p:presentation>',
    '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldSz cx="1" cy="2"/><p:sldSz cx="1" cy="2"/></p:presentation>',
    'x'*262145])
def test_untrusted_presentation_xml_refused_in_bounded_child(tmp_path,xml):
    m=module();source=tmp_path/'s.pdf';pdf(source);deck=tmp_path/'x.pptx';pptx(deck,xml)
    with pytest.raises(m.subprocess.SubprocessError):m.raw_metadata([source]*3,deck,0,tmp_path,m.guard.Deadline(10))


def test_expired_budget_invalid_page_and_fifo_fail_closed(tmp_path):
    m=module()
    for page,seconds in [(0,120),(True,120),(201,120),(1,0),(1,float('nan'))]:
        r=m.diagnose('missing','missing','missing','missing',page,[],timeout=seconds)
        assert not r['geometry_proven'] and not r['production_acceptance'] and 'reason' in r
    if hasattr(os,'mkfifo'):
        path=tmp_path/'pipe';os.mkfifo(path)
        r=m.diagnose(path,path,path,path,1,[[1,1,2,2]])
        assert not r['geometry_proven'] and 'reason' in r


@pytest.mark.skipif(not os.getenv('SMARTPPT_TEST_RENDERER'),reason='real Office renderer required')
def test_real_quantized_canvas_is_diagnostic_only_and_default_guard_stays_strict(tmp_path):
    from smartppt.config import Settings
    from smartppt.pdf import inspect_pdf
    from smartppt.preserve import convert_preserve
    from smartppt.render_gate import render_presentations
    m=module();source=tmp_path/'source.pdf';pdf(source);deck=tmp_path/'candidate.pptx'
    convert_preserve(source,deck,inspect_pdf(source))
    actual=render_presentations([deck],tmp_path,Settings(renderer_path=os.environ['SMARTPPT_TEST_RENDERER']))[0]
    boxes=[[50,100,90,115]]
    strict=m.guard.evaluate(source,0,actual,0,actual,0,(400,400),boxes)
    assert strict['accepted'] is False and strict['reason']=='page_dimensions_differ'
    result=m.diagnose(source,actual,actual,deck,1,boxes)
    assert result['geometry_proven'] and result['all_visual_nonregressing']
    assert result['nonregressing_rois']==[True] and len(result['samples'])==4
    assert result['production_acceptance'] is False and result['diagnostic_only'] is True
    # Same ordinary guard still refuses after diagnostic work; no monkeypatch,
    # mutated PDF geometry, persisted global override or image registration.
    assert m.guard.evaluate(source,0,actual,0,actual,0,(400,400),boxes)['reason']=='page_dimensions_differ'


def test_expanded_crop_must_fit_physical_output_not_ceil_png(tmp_path,monkeypatch):
    m=module()
    monkeypatch.setattr(m.guard,'_snapshot',lambda path,target,deadline:target)
    monkeypatch.setattr(m.guard,'_metadata',lambda path,index,folder,label,deadline:[400,400] if label=='source' else [399.9968566894531]*2)
    monkeypatch.setattr(m,'raw_metadata',lambda *a:{'emu':[5080000]*2,'pages':[{}]*3})
    monkeypatch.setattr(m,'prove',lambda *a:{'source_size':['400','400'],'serialized_output_size':['399.99685','399.99685']})
    monkeypatch.setattr(m.guard,'_raster',lambda *a:pytest.fail('must reject before raster'))
    # Ink is inside output; integer crop rounds outward to x=400.
    result=m.diagnose('a','b','c','d',1,[[397,10,398.5,20]])
    assert result['reason']=='expanded_roi_outside_page'
    assert not result['geometry_proven']
    assert not result['production_acceptance'] and not result['samples']


def test_parser_child_gets_resource_limits_and_remaining_timeout(tmp_path,monkeypatch):
    m=module();seen={}
    def run(argv,**kwargs):
        seen.update(kwargs);kwargs['stdout'].write(b'{"pages":[],"emu":[]}')
    monkeypatch.setattr(m.subprocess,'run',run)
    m.raw_metadata([Path('a')]*3,Path('b'),0,tmp_path,m.guard.Deadline(1))
    assert 0<seen['timeout']<=1 and seen['preexec_fn'] is m._limits
    assert seen['stderr'].closed and seen['stdout'].closed


def test_raw_decimal_lexemes_are_not_rounded_through_float(tmp_path):
    m=module();source=tmp_path/'s.pdf';pdf(source)
    # Preserve offsets by replacing with same-length tokens where possible;
    # use pypdf to write a RawObject token for controlled valid PDF metadata.
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import PdfObject,NameObject,ArrayObject,NumberObject
    class Token(PdfObject):
        def write_to_stream(self,stream,*args):stream.write(b'1.00000000000000000001')
    reader=PdfReader(source);writer=PdfWriter();page=writer.add_page(reader.pages[0]);page[NameObject('/UserUnit')]=Token()
    with source.open('wb') as stream:writer.write(stream)
    deck=tmp_path/'x.pptx';pptx(deck,'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldSz cx="5080000" cy="5080000"/></p:presentation>')
    data=m.raw_metadata([source]*3,deck,0,tmp_path,m.guard.Deadline(10))
    assert data['pages'][0]['user_unit']=='1.00000000000000000001'
    from smartppt.canvas_quantization import prove,Refused
    with pytest.raises(Refused,match='unsupported_page'):
        prove([5080000]*2,[400.,400.],*data['pages'],[[50,100,90,115]])

@pytest.mark.parametrize('token',[b'1.'+b'0'*64,b'1.00000000000000000001'])
def test_decimal_length_bound_and_raw_media_precision(tmp_path,token):
    m=module();source=tmp_path/'s.pdf';pdf(source)
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import PdfObject,NameObject,ArrayObject,NumberObject
    class Token(PdfObject):
        def write_to_stream(self,stream,*args):stream.write(token)
    reader=PdfReader(source);writer=PdfWriter();page=writer.add_page(reader.pages[0]);page[NameObject('/MediaBox')]=ArrayObject([NumberObject(0),NumberObject(0),Token(),NumberObject(400)])
    with source.open('wb') as stream:writer.write(stream)
    deck=tmp_path/'x.pptx';pptx(deck,'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldSz cx="5080000" cy="5080000"/></p:presentation>')
    if len(token)>64:
        with pytest.raises(m.subprocess.SubprocessError):m.raw_metadata([source]*3,deck,0,tmp_path,m.guard.Deadline(10))
    else:
        data=m.raw_metadata([source]*3,deck,0,tmp_path,m.guard.Deadline(10))
        assert data['pages'][0]['media_box'][2]==token.decode()
        assert data['pages'][0]['crop_box']==data['pages'][0]['media_box']

def test_same_grid_but_output_parser_disagreement_refused(tmp_path,monkeypatch):
    m=module()
    monkeypatch.setattr(m.guard,'_snapshot',lambda path,target,deadline:target)
    monkeypatch.setattr(m.guard,'_metadata',lambda *a:[399.9968]*2)
    monkeypatch.setattr(m,'raw_metadata',lambda *a:{'emu':[5080000]*2,'pages':[{}]*3})
    monkeypatch.setattr(m,'prove',lambda *a:{'source_size':['400','400'],'serialized_output_size':['399.996850393701']*2})
    monkeypatch.setattr(m.guard,'_raster',lambda *a:pytest.fail('must reject before raster'))
    result=m.diagnose('a','b','c','d',1,[[50,100,90,115]])
    assert result['reason']=='output_parser_disagreement'
    assert not result['geometry_proven'] and not result['production_acceptance']
