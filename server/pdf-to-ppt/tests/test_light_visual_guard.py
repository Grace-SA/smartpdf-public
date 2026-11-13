"""Unknown or worse cross-engine ink must never admit an additive candidate."""
import json,os,shutil,subprocess
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from smartppt import light_visual_guard as guard


def image(offset=0,alter=False):
    im=Image.new('RGB',(100,80),'white');draw=ImageDraw.Draw(im)
    draw.rectangle((30+offset,30,40+offset,50),fill='black')
    if alter:draw.rectangle((34+offset,34,36+offset,46),fill='white')
    return im


def test_metrics_identity_shift_and_same_bounds_alteration():
    a=image();same=guard.metrics(a,a,3);shift=guard.metrics(a,image(3),3);different=guard.metrics(a,image(alter=True),3)
    assert same=={'mae':0,'foreground_mae':0,'edge_error_points':0}
    assert shift['edge_error_points']==1 and shift['foreground_mae']>0
    assert different['edge_error_points']==0 and different['foreground_mae']>0

@pytest.mark.parametrize('kind',['empty','dirty','background'])
def test_unknown_crop_refused(kind):
    a=image();b=image()
    if kind=='empty':b=Image.new('RGB',a.size,'white')
    elif kind=='dirty':b.putpixel((0,0),(0,0,0))
    else:
        b=Image.new('RGB',a.size,(200,200,200));ImageDraw.Draw(b).rectangle((30,30,40,50),fill='black')
    with pytest.raises(guard.Refused):guard.metrics(a,b,3)


def test_outside_union_is_exact_and_boundary_exclusive():
    a=image();b=a.copy();b.putpixel((20,20),(0,0,0))
    assert guard._outside_equal(a,b,[(10,10,21,21)],1)
    assert not guard._outside_equal(a,b,[(10,10,20,20)],1)
    b.putpixel((90,70),(0,0,0))
    assert not guard._outside_equal(a,b,[(10,10,21,21)],1)

@pytest.mark.parametrize('size,boxes',[((2000,2000),[(20,20,30,30)]),((100,100),[]),
    ((100,100),[(20,20,30,30)]*65),((100,100),[(0,10,10,20)]),
    ((100,100),[(20,20,float('nan'),30)]),((612,792),[(10,10,600,700)]),
    ((600,600),[(20,20,80,80)]*20)])
def test_resource_preflight_rejects(size,boxes):
    with pytest.raises(guard.Refused):guard._rois(size,boxes)


def test_fixed_integer_physical_rois():
    assert guard._rois((100,100),[(20.2,40.3,30.1,50.8)])==[(19,48,32,61)]
    for dpi in guard.DPIS:
        assert all(int(v*dpi/72)==v*dpi/72 for v in (19,48,32,61))

@pytest.mark.parametrize('seconds',[0,-1,121,float('nan')])
def test_bad_deadline_refuses_instead_of_throwing(seconds):
    assert not guard.verify(None,0,None,0,None,0,(100,100),[(10,10,20,20)],timeout=seconds)


def fake_run(monkeypatch,tmp_path,*,failure=None):
    for name in ['s','p','c']:(tmp_path/name).write_bytes(b'fake')
    monkeypatch.setattr(guard.shutil,'which',lambda _: '/usr/bin/pdftoppm')
    monkeypatch.setattr(guard,'_metadata',lambda *a:[100,100])
    snapshots=[];original=guard._snapshot
    def snapshot(*args):snapshots.append(args[1]);return original(*args)
    monkeypatch.setattr(guard,'_snapshot',snapshot)
    calls=[]
    def raster(path,index,dpi,size,folder,label,deadline):
        calls.append((label,dpi));im=Image.new('RGB',(int(100*dpi/72),)*2,'white')
        scale=dpi/72;draw=ImageDraw.Draw(im);draw.rectangle((30*scale,30*scale,35*scale,40*scale),fill='black')
        if label.startswith('candidate') and failure=='outside':im.putpixel((0,0),(0,0,0))
        if label.startswith('candidate') and failure=='one_dpi' and dpi==288:im=Image.new('RGB',im.size,'white')
        return im
    monkeypatch.setattr(guard,'_raster',raster)
    return calls,snapshots

@pytest.mark.parametrize('failure,accepted',[(None,True),('outside',False),('one_dpi',False)])
def test_full_four_resolution_transaction_and_cleanup(monkeypatch,tmp_path,failure,accepted):
    calls,snapshots=fake_run(monkeypatch,tmp_path,failure=failure)
    assert guard.verify(tmp_path/'s',0,tmp_path/'p',0,tmp_path/'c',0,(100,100),[(29,59,36,71)]) is accepted
    if accepted:assert [dpi for _,dpi in calls]==[dpi for dpi in guard.DPIS for _ in range(3)]
    assert snapshots and all(not path.exists() and not path.parent.exists() for path in snapshots)
    assert all((tmp_path/n).read_bytes()==b'fake' for n in ['s','p','c'])


def test_dimensions_rotation_and_metadata_refusal(monkeypatch,tmp_path):
    fake_run(monkeypatch,tmp_path)
    monkeypatch.setattr(guard,'_metadata',lambda *a:[100,101])
    monkeypatch.setattr(guard,'_raster',lambda *a:pytest.fail('no raster after dimension refusal'))
    assert not guard.verify(tmp_path/'s',0,tmp_path/'p',0,tmp_path/'c',0,(100,100),[(20,20,30,30)])


def test_subprocess_deadline_stderr_disk_and_file_limit(monkeypatch,tmp_path):
    recorded={}
    def run(command,**kwargs):recorded.update(kwargs)
    monkeypatch.setattr(guard.subprocess,'run',run)
    guard._run(['pdftoppm'],tmp_path,'case',guard.Deadline(10))
    assert 0<recorded['timeout']<=10 and recorded['stderr']!=subprocess.PIPE
    assert callable(recorded['preexec_fn']) and recorded['stdout']==subprocess.DEVNULL
    assert recorded['stderr'].closed


def test_missing_tool_or_subprocess_failure_refuses(monkeypatch,tmp_path):
    monkeypatch.setattr(guard.shutil,'which',lambda _:None)
    assert not guard.verify(None,0,None,0,None,0,(100,100),[(20,20,30,30)])
    fake_run(monkeypatch,tmp_path)
    monkeypatch.setattr(guard,'_metadata',lambda *a: (_ for _ in ()).throw(subprocess.TimeoutExpired('pdf',1)))
    assert not guard.verify(tmp_path/'s',0,tmp_path/'p',0,tmp_path/'c',0,(100,100),[(20,20,30,30)])


def test_input_size_and_regular_file_bounds(tmp_path):
    path=tmp_path/'huge'
    with path.open('wb') as out:out.truncate(guard.MAX_BYTES+1)
    with pytest.raises(guard.Refused):guard._snapshot(path,tmp_path/'out',guard.Deadline(1))
    with pytest.raises((guard.Refused,OSError)):guard._snapshot(tmp_path,tmp_path/'out',guard.Deadline(1))

@pytest.mark.skipif(not shutil.which('pdftoppm') or os.name!='posix',reason='bounded Poppler required')
def test_actual_pdf_identity_and_shift_refusal(tmp_path):
    from reportlab.pdfgen import canvas
    source=tmp_path/'source.pdf';shift=tmp_path/'shift.pdf'
    for path,y in [(source,50),(shift,51)]:
        c=canvas.Canvas(str(path),pagesize=(100,100));c.setFont('Helvetica',10);c.drawString(20,y,'Test');c.save()
    args=[source,0,source,0,source,0,(100,100),[(19,47,42,59)]]
    assert guard.verify(*args)
    args[4]=shift
    assert not guard.verify(*args)
    args[4]=source;args[5]=1
    assert not guard.verify(*args)


def two_roi_setup(monkeypatch,tmp_path,*,bad='regression',outside=False):
    calls,snapshots=fake_run(monkeypatch,tmp_path)
    calls.clear()
    def raster(path,index,dpi,size,folder,label,deadline):
        calls.append((label,dpi));scale=dpi/72
        im=Image.new('RGB',(int(100*scale),)*2,'white');draw=ImageDraw.Draw(im)
        for x in [20,60]:draw.rectangle((x*scale,30*scale,(x+5)*scale,40*scale),fill='black')
        if label.startswith('candidate'):
            if bad=='regression':draw.rectangle((62*scale,32*scale,63*scale,38*scale),fill='white')
            elif bad=='empty':draw.rectangle((58*scale,28*scale,67*scale,42*scale),fill='white')
            elif bad=='dirty':im.putpixel((int(58*scale),int(28*scale)),(0,0,0))
            if outside and dpi==432:im.putpixel((0,0),(0,0,0))
        return im
    monkeypatch.setattr(guard,'_raster',raster)
    args=(tmp_path/'s',0,tmp_path/'p',0,tmp_path/'c',0,(100,100),[(19,59,26,71),(59,59,66,71)])
    return args,calls,snapshots

@pytest.mark.parametrize('bad',['regression','empty','dirty'])
def test_assess_keeps_good_roi_but_verify_still_short_circuits(monkeypatch,tmp_path,bad):
    args,calls,snapshots=two_roi_setup(monkeypatch,tmp_path,bad=bad)
    assert guard.assess(*args)==[True,False]
    assert len(calls)==12 # one source/previous/candidate render per DPI
    assert all(not path.exists() for path in snapshots)
    calls.clear()
    assert not guard.verify(*args)
    assert len(calls)==3 # unchanged whole-candidate rejection on first DPI


def test_assess_global_outside_change_after_local_failure_is_not_hidden(monkeypatch,tmp_path):
    args,calls,_=two_roi_setup(monkeypatch,tmp_path,outside=True)
    assert guard.assess(*args) is None
    assert len(calls)==12 # must still inspect final-DPI outside pixels


def test_assess_identity_and_deadline_global_refusal(monkeypatch,tmp_path):
    args,calls,_=two_roi_setup(monkeypatch,tmp_path,bad=None)
    assert guard.assess(*args)==[True,True]
    calls.clear();assert guard.assess(*args,timeout=0) is None and calls==[]
    count=[0]
    def expired(self):
        count[0]+=1
        if count[0]>10:raise guard.Refused('time_budget')
        return 1
    monkeypatch.setattr(guard.Deadline,'remaining',expired)
    assert guard.assess(*args) is None


def test_assess_parser_grid_uncertainty_is_global(monkeypatch,tmp_path):
    args,_,_=two_roi_setup(monkeypatch,tmp_path)
    monkeypatch.setattr(guard,'metrics',lambda *_: (_ for _ in ()).throw(guard.Refused('crop_grid_mismatch')))
    assert guard.assess(*args) is None
