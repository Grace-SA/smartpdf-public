"""Independent ink diagnostics must abstain rather than fabricate alignment."""
import importlib.util
from pathlib import Path
import subprocess
import pytest
from PIL import Image,ImageDraw

@pytest.fixture
def ink():
 path=Path(__file__).parents[1]/'tools'/'public-native-ink.py'
 spec=importlib.util.spec_from_file_location('public_native_ink',path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module


def glyph():
 image=Image.new('RGB',(80,60),'white');d=ImageDraw.Draw(image)
 for box in ((20,15,23,44),(40,15,43,44),(24,27,39,32)):d.rectangle(box,fill='black')
 return image


def test_identical_ink_and_shift_are_distinguished(ink):
 a=glyph();assert ink.ink_metrics(a,a)['ink_within_diagnostic_bounds']
 shifted=Image.new('RGB',a.size,'white');shifted.paste(a,(3,0))
 result=ink.ink_metrics(a,shifted)
 assert result['ink_edge_error_points']==1 and not result['ink_within_diagnostic_bounds']


def test_changed_same_bounds_glyph_rejected(ink):
 a=glyph();b=a.copy();ImageDraw.Draw(b).rectangle((24,27,39,32),fill='white')
 result=ink.ink_metrics(a,b)
 assert result['ink_edge_error_points']==0 and not result['ink_within_diagnostic_bounds']


@pytest.mark.parametrize('kind',['border','empty','size'])
def test_ambiguous_raster_abstains(ink,kind):
 a=glyph();b=a.copy()
 if kind=='border':b.putpixel((0,0),(0,0,0))
 if kind=='empty':b=Image.new('RGB',a.size,'white')
 if kind=='size':b=b.resize((81,60))
 assert ink.ink_metrics(a,b)['status']=='abstain'


def test_neighbor_and_missing_pair_abstain(ink):
 s={'text':'H','bbox':[5,4,16,16]};p=dict(s)
 row={'source':s,'rendered':p,'exact_text':True};a=glyph()
 neighbor={'text':'X','bbox':[15,4,20,16]}
 assert ink.measure(a,a,row,[s,neighbor],[p])['reason']=='neighbor_box_intersection'
 row['rendered']=None
 assert ink.measure(a,a,row,[s],[p])['reason']=='no_geometry_pair'


def test_matching_text_never_relocates_word(ink):
 source=[{'text':'123','bbox':[0,0,10,10]},{'text':'456','bbox':[100,0,110,10]}]
 output=[dict(source[0],text='456'),dict(source[1],text='123')]
 assert not any(r['exact_text'] for r in ink.pair_words(source,output))
 duplicate=[source[0],dict(source[0])]
 assert all(r['rendered'] is None for r in ink.pair_words(duplicate,duplicate))


@pytest.mark.parametrize('kind',['pages','dimensions','pixels','nonfinite','wordcount'])
def test_resource_and_coordinate_guards(ink,kind):
 a=[((200,200),[])];b=[((200,200),[])]
 if kind=='pages':b*=2
 if kind=='dimensions':b=[((201,200),[])]
 if kind=='pixels':a=b=[((100000,100000),[])]
 if kind=='nonfinite':a=b=[((float('nan'),200),[])]
 if kind=='wordcount':a=b=[((200,200),[{'text':'A','bbox':[0,0,1,1]}]*(ink.MAX_WORDS+1))]
 with pytest.raises(ValueError):ink.validate_pages(a,b)


def test_render_timeout_is_bounded(ink,tmp_path,monkeypatch):
 def run(command,**kwargs):
  assert kwargs['timeout']==60
  raise subprocess.TimeoutExpired(command,60)
 monkeypatch.setattr(ink.subprocess,'run',run)
 with pytest.raises(subprocess.TimeoutExpired):ink.raster(tmp_path/'input.pdf',1,tmp_path/'output',(200,200))


def test_pixel_grid_mismatch_abstains_and_temp_is_cleaned(ink,tmp_path,monkeypatch):
 from types import SimpleNamespace
 source=tmp_path/'source.pdf';rendered=tmp_path/'rendered.pdf'
 source.write_bytes(b'local fixture');rendered.write_bytes(b'local fixture')
 monkeypatch.setattr(ink,'bounded_words',lambda *args: [((20,20),[])])
 folders=[]
 def raster(path,number,prefix,dimensions):
  folders.append(prefix.parent)
  return Image.new('RGB',(60 if path==source else 61,60),'white')
 monkeypatch.setattr(ink,'raster',raster)
 result=ink.diagnose(source,rendered)
 assert result['pages'][0]['reason']=='different_page_pixel_dimensions'
 assert result['no_acceptance_verdict'] and not result['strict_bbox_results_modified']
 assert all(not p.exists() for p in folders)


def test_existing_output_is_never_overwritten(ink,tmp_path,monkeypatch):
 import sys
 output=tmp_path/'evidence.json';output.write_text('original')
 monkeypatch.setattr(sys,'argv',['ink','--source','x.pdf','--rendered','y.pdf','--output',str(output)])
 with pytest.raises(FileExistsError):ink.main()
 assert output.read_text()=='original'


def test_xml_extraction_page_byte_and_child_limits(ink,tmp_path,monkeypatch):
 xml=b'<html xmlns="http://www.w3.org/1999/xhtml"><page width="20" height="20"><word xMin="1" yMin="2" xMax="3" yMax="4">A</word></page></html>'
 def run(argv,**kwargs):
  assert argv[1:5]==['-f','1','-l',str(ink.MAX_PAGES+1)]
  assert kwargs['timeout']==60 and callable(kwargs['preexec_fn'])
  kwargs['stdout'].write(xml)
 monkeypatch.setattr(ink.subprocess,'run',run)
 assert ink.bounded_words(tmp_path/'source.pdf',tmp_path,'source')==[((20,20),[{'text':'A','bbox':[1,2,3,4]}])]
 monkeypatch.setattr(ink,'MAX_XML_BYTES',len(xml)-1)
 with pytest.raises(ValueError,match='XML byte'):ink.bounded_words(tmp_path/'source.pdf',tmp_path,'large')


def test_extraction_failure_cleans_temporary_files(ink,tmp_path,monkeypatch):
 source=tmp_path/'source.pdf';source.write_bytes(b'fixture');folders=[]
 def bounded(path,folder,label):
  folders.append(folder);(folder/'partial.xml').write_bytes(b'partial')
  raise ValueError('XML byte resource bound exceeded')
 monkeypatch.setattr(ink,'bounded_words',bounded)
 with pytest.raises(ValueError,match='XML byte'):ink.diagnose(source,source)
 assert folders and all(not p.exists() for p in folders)


def test_non_posix_protection_is_explicitly_unsupported(ink,monkeypatch):
 monkeypatch.setattr(ink.os,'name','unsupported')
 with pytest.raises(RuntimeError,match='requires POSIX'):ink.extraction_limit()
