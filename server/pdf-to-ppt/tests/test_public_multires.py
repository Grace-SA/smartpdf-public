"""Fixed physical observations must not become an alignment or acceptance waiver."""
import importlib.util
from pathlib import Path
import pytest
from PIL import Image,ImageDraw

@pytest.fixture
def tool():
 path=Path(__file__).parents[1]/'tools'/'public-native-multires.py'
 spec=importlib.util.spec_from_file_location('public_multires',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module


def glyph(scale):
 image=Image.new('RGB',(int(80*scale),int(60*scale)),'white');draw=ImageDraw.Draw(image)
 for l,t,r,b in ((20,15,24,45),(40,15,44,45),(24,27,40,33)):
  draw.rectangle((l*scale,t*scale,r*scale-1,b*scale-1),fill='black')
 return image


@pytest.mark.parametrize('dpi',[144,216,288,432])
def test_fixed_point_shift_and_single_pixel_phase(tool,dpi):
 ink=tool.load_ink(dpi);source=glyph(ink.SCALE)
 shifted=Image.new('RGB',source.size,'white');shifted.paste(source,(int(ink.SCALE),0))
 result=tool.measurements(ink,source,shifted)
 assert result['signed_edges_points']==[1,0,1,0]
 assert result['ink_edge_error_points']==1
 phase=Image.new('RGB',source.size,'white');phase.paste(source,(1,0))
 result=tool.measurements(ink,source,phase)
 assert result['signed_edges_points']==[72/dpi,0,72/dpi,0]
 assert 'ink_within_diagnostic_bounds' not in result


def test_changed_glyph_same_outer_bounds_is_not_hidden(tool):
 ink=tool.load_ink(216);a=glyph(3);b=a.copy()
 ImageDraw.Draw(b).rectangle((24*3,27*3,40*3-1,33*3-1),fill='white')
 result=tool.measurements(ink,a,b)
 assert result['ink_edge_error_points']==0
 assert result['foreground_mae']>.1 and result['mask_iou']<.9


def observed(dpi):
 value={'status':'observed','ink_edge_error_points':1.,'foreground_mae':.2,'mask_iou':.7,'signed_edges_points':[1,0,1,0]}
 return {'dpi':dpi,'candidate':dict(value),'baseline':dict(value)}


def test_common_subset_requires_all_resolutions_both_controls_and_exact_text(tool):
 rows=[{'exact_text':True,'samples':[observed(d) for d in tool.DPIS]} for _ in range(4)]
 rows[1]['samples'][2]['baseline']={'status':'abstain','reason':'non_solid_border'}
 rows[2]['exact_text']=False
 rows[3]['samples'][0]={'dpi':144,'status':'abstain','reason':'pixel_grid_mismatch'}
 summary=tool.summarize(rows)
 assert summary['common_observed_word_indices']==[0]
 assert summary['resolution_summary'][0]['candidate']['foreground_mae']==.2
 assert summary['resolution_summary'][0]['baseline']['foreground_mae']==.2 # never subtracted
 assert rows[1]['samples'][2]['baseline']['reason']=='non_solid_border'


def test_physical_roi_frozen_and_text_cannot_relocate_pair(tool):
 ink=tool.load_ink(432)
 a={'text':'123','bbox':[10.2,20.1,20.3,30.4]};b={'text':'456','bbox':[10.3,20.2,20.4,30.5]}
 rows=tool.fixed_rows(ink,(200,200),[a],[b])
 assert rows[0]['roi_points']==[9,19,22,32] and not rows[0]['exact_text']
 assert all(all((v*d/72).is_integer() for v in map(float,rows[0]['roi_points'])) for d in tool.DPIS)


def test_old_216_module_constants_and_metrics_untouched(tool):
 original=tool.load_ink(216);a=glyph(3);before=original.ink_metrics(a,a)
 for dpi in tool.DPIS:tool.measurements(tool.load_ink(dpi),glyph(dpi/72),glyph(dpi/72))
 assert original.DPI==216 and original.SCALE==3 and original.ink_metrics(a,a)==before
 assert original.ink_metrics(a,a)['ink_within_diagnostic_bounds']


def test_deadline_controls_subprocess_timeout(tool,monkeypatch):
 clock=[100.];monkeypatch.setattr(tool.time,'monotonic',lambda:clock[0]);deadline=tool.Deadline(5)
 timeouts=[]
 monkeypatch.setattr(tool.subprocess,'run',lambda *a,**k:timeouts.append(k['timeout']))
 deadline.run(['test'],timeout=60);assert timeouts==[5]
 clock[0]=106.
 with pytest.raises(TimeoutError):deadline.run(['test'])


def test_streaming_hash_limit(tool,tmp_path):
 p=tmp_path/'file';p.write_bytes(b'abc')
 assert tool.digest(p,3,tool.Deadline())=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
 with pytest.raises(ValueError,match='file resource'):tool.digest(p,2,tool.Deadline())
 with pytest.raises(ValueError,match='regular file'):tool.digest(tmp_path,100,tool.Deadline())


def fake_inputs(tool,tmp_path,monkeypatch,dimensions=(200,200),baseline_words=False):
 paths=[tmp_path/(name+'.pdf') for name in ('source','rendered','baseline')]
 for p in paths:p.write_bytes(b'fixture')
 ink=tool.load_ink(432);folders=[]
 word={'text':'A','bbox':[10,10,20,20]}
 def words(path,folder,label):
  folders.append(folder)
  return [(dimensions,[] if label=='baseline' and not baseline_words else [word])]
 monkeypatch.setattr(ink,'bounded_words',words)
 monkeypatch.setattr(tool,'load_ink',lambda *a,**k:ink)
 monkeypatch.setattr(tool,'versions',lambda deadline:{'test':'test'})
 return paths,ink,folders


def test_highest_dpi_resource_bound_checked_before_raster(tool,tmp_path,monkeypatch):
 paths,ink,folders=fake_inputs(tool,tmp_path,monkeypatch,dimensions=(1000,1000))
 monkeypatch.setattr(ink,'raster',lambda *a:pytest.fail('must fail 432dpi preflight before raster'))
 with pytest.raises(ValueError,match='pixel resource'):tool.diagnose(*paths)
 assert all(not f.exists() for f in folders)


def test_non_image_baseline_rejected_and_temp_cleaned(tool,tmp_path,monkeypatch):
 paths,ink,folders=fake_inputs(tool,tmp_path,monkeypatch,baseline_words=True)
 monkeypatch.setattr(ink,'raster',lambda *a:pytest.fail('text baseline must not raster'))
 with pytest.raises(ValueError,match='zero extractable'):tool.diagnose(*paths)
 assert all(not f.exists() for f in folders)


def test_raster_failure_cleans_partial_temp_outputs(tool,tmp_path,monkeypatch):
 paths,ink,folders=fake_inputs(tool,tmp_path,monkeypatch)
 def raster(path,number,prefix,dimensions):
  prefix.with_suffix('.png').write_bytes(b'partial')
  raise TimeoutError('raster expired')
 monkeypatch.setattr(ink,'raster',raster)
 with pytest.raises(TimeoutError):tool.diagnose(*paths)
 assert all(not f.exists() for f in folders)


def test_output_exclusive(tool,tmp_path,monkeypatch):
 import sys
 output=tmp_path/'result.json';output.write_text('existing')
 monkeypatch.setattr(sys,'argv',['multi','--source','s','--rendered','r','--baseline','b','--output',str(output)])
 with pytest.raises(FileExistsError):tool.main()
 assert output.read_text()=='existing'


def test_serialization_deadline_removes_only_incomplete_new_output(tool,tmp_path,monkeypatch):
 import sys
 output=tmp_path/'new.json';calls=[]
 class Budget:
  def remaining(self):
   calls.append(1)
   if len(calls)>1:raise TimeoutError('budget expired while writing')
   return 1
 monkeypatch.setattr(tool,'Deadline',Budget)
 monkeypatch.setattr(tool,'diagnose',lambda *a,**k:{'diagnostic_only':True})
 monkeypatch.setattr(sys,'argv',['multi','--source','s','--rendered','r','--baseline','b','--output',str(output)])
 with pytest.raises(TimeoutError):tool.main()
 assert not output.exists()


def test_snapshot_keeps_hashed_bytes_when_original_changes(tool,tmp_path):
 source=tmp_path/'source';snapshot=tmp_path/'snapshot.pdf';source.write_bytes(b'abc')
 digest=tool.copy_and_digest(source,snapshot,100,tool.Deadline())
 source.write_bytes(b'changed')
 assert snapshot.read_bytes()==b'abc'
 assert tool.digest(snapshot,100,tool.Deadline())==digest
 with pytest.raises(FileExistsError):tool.copy_and_digest(source,snapshot,100,tool.Deadline())


@pytest.mark.skipif(__import__('os').name!='posix',reason='POSIX FIFO')
def test_fifo_is_rejected_without_waiting_for_writer(tool,tmp_path):
 import os
 path=tmp_path/'fifo';os.mkfifo(path)
 with pytest.raises(ValueError,match='regular file'):tool.digest(path,100,tool.Deadline())


def test_cleanup_does_not_delete_replacement_output(tool,tmp_path,monkeypatch):
 import sys
 output=tmp_path/'result.json';calls=[]
 class Budget:
  def remaining(self):
   calls.append(1)
   if len(calls)>1:
    output.unlink();output.write_text('another writer')
    raise TimeoutError('interrupted')
   return 1
 monkeypatch.setattr(tool,'Deadline',Budget)
 monkeypatch.setattr(tool,'diagnose',lambda *a,**k:{'diagnostic_only':True})
 monkeypatch.setattr(sys,'argv',['multi','--source','s','--rendered','r','--baseline','b','--output',str(output)])
 with pytest.raises(TimeoutError):tool.main()
 assert output.read_text()=='another writer'


@pytest.mark.parametrize('seconds',[0,-1,float('nan'),float('inf'),601])
def test_invalid_wall_budget_rejected(tool,seconds):
 with pytest.raises(ValueError,match='time budget'):tool.Deadline(seconds)


def test_renderer_stderr_not_captured_in_unbounded_memory(tool,monkeypatch):
 seen=[]
 def run(command,**kwargs):
  assert kwargs['stderr']!=tool.subprocess.PIPE
  assert callable(kwargs['preexec_fn'])
  kwargs['stderr'].write(b'bounded diagnostic error')
  seen.append(kwargs['stderr'])
 monkeypatch.setattr(tool.subprocess,'run',run)
 tool.Deadline().run(['pdftoppm'],stderr=tool.subprocess.PIPE)
 assert seen[0].closed


def test_engine_versions_are_bounded_and_recorded(tool,monkeypatch):
 def run(command,**kwargs):kwargs['stdout'].write((command[0]+' version test\nnotice').encode())
 monkeypatch.setattr(tool.subprocess,'run',run)
 assert tool.versions(tool.Deadline())=={'pdftotext':'pdftotext version test','pdftoppm':'pdftoppm version test'}
