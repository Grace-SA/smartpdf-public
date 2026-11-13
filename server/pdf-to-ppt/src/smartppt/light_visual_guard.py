"""Additional fail-closed Poppler nonregression check for a final page candidate.

This never replaces source ownership, content, PDFium geometry/local/page gates.
Callers supply already-verified source ink boxes in normalized lower-left points.
No matching, registration, resampling, fitting, or mutation occurs here.
"""
import json,math,os,shutil,stat,subprocess,sys,tempfile,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageChops,ImageDraw

DPIS=(144,216,288,432)
MAX_BYTES=64*1024*1024
MAX_PIXELS=20_000_000
MAX_EDGE=10000
MAX_ROIS=64
MAX_ROI_PIXELS=200_000
MAX_TOTAL_ROI_PIXELS=2_000_000
MAX_PAGES=200
EPSILON=1e-12

class Refused(ValueError):pass

class Deadline:
    def __init__(self,seconds):
        if not math.isfinite(seconds) or not 0<seconds<=120:raise Refused('invalid_time_budget')
        self.end=time.monotonic()+seconds
    def remaining(self):
        result=self.end-time.monotonic()
        if result<=0:raise Refused('time_budget')
        return result

def _limit():
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_BYTES,MAX_BYTES))

def _run(command,folder,label,deadline,*,stdout=None):
    if os.name!='posix':raise Refused('posix_required')
    import resource
    if not hasattr(resource,'RLIMIT_FSIZE'):raise Refused('file_limit_unavailable')
    with (folder/(label+'.stderr')).open('xb') as error:
        subprocess.run(command,stdout=stdout if stdout is not None else subprocess.DEVNULL,
                       stderr=error,check=True,timeout=min(30,deadline.remaining()),preexec_fn=_limit)
    deadline.remaining()

def _snapshot(path,target,deadline):
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NONBLOCK',0))
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=MAX_BYTES:raise Refused('input_resource_limit')
        stream=os.fdopen(descriptor,'rb')
    except BaseException:
        os.close(descriptor);raise
    total=0
    with stream,target.open('xb') as output:
        while chunk:=stream.read(1024*1024):
            deadline.remaining();total+=len(chunk)
            if total>MAX_BYTES:raise Refused('input_resource_limit')
            output.write(chunk)
    return target

# Parse in a bounded child too: malformed input cannot strand the service in a
# native parser call past the guard's wall deadline. Only selected-page metadata
# is emitted, never arbitrary source text.
_METADATA="""import sys,json,pypdfium2 as p
from contextlib import closing
with p.PdfDocument(sys.argv[1]) as doc:
 n=len(doc);i=int(sys.argv[2])
 if not 0<=i<n or n>200:raise ValueError('page_count')
 with closing(doc[i]) as page:print(json.dumps([n,list(page.get_size()),page.get_rotation()]))
"""

def _metadata(path,index,folder,label,deadline):
    if type(index) is not int or index<0:raise Refused('invalid_page_index')
    output=folder/(label+'.json')
    with output.open('xb') as stream:
        _run([sys.executable,'-c',_METADATA,str(path),str(index)],folder,label,deadline,stdout=stream)
    if output.stat().st_size>1024:raise Refused('metadata_limit')
    count,dimensions,rotation=json.loads(output.read_text())
    if type(count) is not int or not 0<=index<count<=MAX_PAGES or rotation!=0:raise Refused('unsupported_page')
    return dimensions

def _rois(page_size,boxes):
    if len(page_size)!=2 or not all(math.isfinite(v) and v>0 for v in page_size):raise Refused('invalid_page_size')
    size=[math.ceil(v*6) for v in page_size]
    if max(size)>MAX_EDGE or math.prod(size)>MAX_PIXELS:raise Refused('page_pixel_limit')
    if not 0<len(boxes)<=MAX_ROIS:raise Refused('roi_count_limit')
    result=[];total=0;w,h=page_size
    for box in boxes:
        if len(box)!=4 or not all(math.isfinite(v) for v in box):raise Refused('invalid_source_box')
        l,b,r,t=box
        if not 0<=l<r<=w or not 0<=b<t<=h:raise Refused('invalid_source_box')
        roi=(math.floor(l)-1,math.floor(h-t)-1,math.ceil(r)+1,math.ceil(h-b)+1)
        if roi[0]<0 or roi[1]<0 or roi[2]>w or roi[3]>h:raise Refused('roi_outside_page')
        area=(roi[2]-roi[0])*(roi[3]-roi[1])*36;total+=area
        if area>MAX_ROI_PIXELS or total>MAX_TOTAL_ROI_PIXELS:raise Refused('roi_pixel_limit')
        result.append(roi)
    return result

def _raster(path,index,dpi,page_size,folder,label,deadline):
    prefix=folder/label
    _run(['pdftoppm','-f',str(index+1),'-l',str(index+1),'-singlefile','-cropbox',
          '-r',str(dpi),'-png',str(path),str(prefix)],folder,label,deadline)
    file=prefix.with_suffix('.png')
    if not file.is_file() or file.stat().st_size>MAX_BYTES:raise Refused('raster_file_limit')
    with Image.open(file) as image:
        expected=tuple(math.ceil(v*dpi/72) for v in page_size)
        if image.size!=expected or max(image.size)>MAX_EDGE or math.prod(image.size)>MAX_PIXELS:
            raise Refused('pixel_grid_mismatch')
        output=image.convert('RGB').copy()
    deadline.remaining();return output

def metrics(source,actual,scale):
    if source.size!=actual.size:raise Refused('crop_grid_mismatch')
    arrays=[np.asarray(im,dtype=np.float32) for im in (source,actual)]
    masks=[];backgrounds=[]
    for array in arrays:
        border=np.concatenate((array[0],array[-1],array[:,0],array[:,-1]))
        background=np.median(border,axis=0);backgrounds.append(background)
        if np.max(np.abs(border-background))>12:raise Refused('dirty_border')
        mask=np.max(np.abs(array-background),axis=2)>20
        if not mask.any():raise Refused('no_ink')
        masks.append(mask)
    if np.max(np.abs(backgrounds[0]-backgrounds[1]))>12:raise Refused('background_changed')
    bounds=[]
    for mask in masks:
        y,x=np.nonzero(mask);bounds.append((x.min(),y.min(),x.max()+1,y.max()+1))
    difference=np.abs(arrays[0]-arrays[1]);foreground=masks[0]|masks[1]
    return {'mae':float(difference.mean(dtype=np.float64)/255),
            'foreground_mae':float(difference[foreground].mean(dtype=np.float64)/255),
            'edge_error_points':max(abs(a-b) for a,b in zip(*bounds))/scale}

def _outside_equal(previous,candidate,rois,scale):
    if previous.size!=candidate.size:return False
    difference=ImageChops.difference(previous,candidate)
    try:
        draw=ImageDraw.Draw(difference)
        for l,t,r,b in rois:draw.rectangle((int(l*scale),int(t*scale),int(r*scale)-1,int(b*scale)-1),fill=(0,0,0))
        return difference.getbbox() is None
    finally:difference.close()

def evaluate(source,source_index,previous,previous_index,candidate,candidate_index,page_size,source_boxes,*,timeout=120):
    result={'accepted':False,'samples':[]}
    try:
        deadline=Deadline(timeout)
        if os.name!='posix' or not shutil.which('pdftoppm'):raise Refused('poppler_or_posix_unavailable')
        rois=_rois(page_size,source_boxes)
        with tempfile.TemporaryDirectory(prefix='smartppt-light-visual-') as temp:
            folder=Path(temp);files=[]
            for label,path,index in [('source',source,source_index),('previous',previous,previous_index),('candidate',candidate,candidate_index)]:
                snapshot=_snapshot(Path(path),folder/(label+'.pdf'),deadline)
                dimensions=_metadata(snapshot,index,folder,label,deadline)
                if len(dimensions)!=2 or any(not math.isfinite(v) for v in dimensions) or max(abs(a-b) for a,b in zip(dimensions,page_size))>1e-4:
                    raise Refused('page_dimensions_differ')
                files.append((label,snapshot,index))
            for dpi in DPIS:
                images=[]
                try:
                    for label,path,index in files:images.append(_raster(path,index,dpi,page_size,folder,label+str(dpi),deadline))
                    if not _outside_equal(images[1],images[2],rois,dpi/72):raise Refused('outside_roi_changed')
                    for i,roi in enumerate(rois):
                        deadline.remaining();box=tuple(int(v*dpi/72) for v in roi)
                        crops=[im.crop(box) for im in images]
                        try:
                            old=metrics(crops[0],crops[1],dpi/72);new=metrics(crops[0],crops[2],dpi/72)
                        finally:
                            for crop in crops:crop.close()
                        result['samples'].append({'dpi':dpi,'roi':i,'previous':old,'candidate':new})
                        if any(new[key]>old[key]+EPSILON for key in old):raise Refused('local_regression')
                finally:
                    for image in images:image.close()
            deadline.remaining();result['accepted']=True
    except (ValueError,TypeError,OSError,RuntimeError,subprocess.SubprocessError,ImportError) as error:
        result['reason']=str(error) or type(error).__name__
    return result

def check(*args,**kwargs):
    return evaluate(*args,**kwargs)['accepted']

# Boolean integration entry point; evaluate is for bounded internal diagnostics.
verify=check


def assess(source,source_index,previous,previous_index,candidate,candidate_index,page_size,source_boxes,*,timeout=120):
    """Return per-ROI eligibility, or None on any global uncertainty.

    This is NOT an acceptance result. Callers must keep complete atomic source
    components, rebuild the final candidate, then call verify on that final PDF.
    Every resolution checks outside the original complete ROI union, even when
    some local ROIs have already failed. Input/ROI policy matches evaluate.
    """
    try:
        deadline=Deadline(timeout)
        if os.name!='posix' or not shutil.which('pdftoppm'):raise Refused('poppler_or_posix_unavailable')
        rois=_rois(page_size,source_boxes);passed=[True]*len(rois)
        with tempfile.TemporaryDirectory(prefix='smartppt-light-assess-') as temp:
            folder=Path(temp);files=[]
            for label,path,index in [('source',source,source_index),('previous',previous,previous_index),('candidate',candidate,candidate_index)]:
                snapshot=_snapshot(Path(path),folder/(label+'.pdf'),deadline)
                dimensions=_metadata(snapshot,index,folder,label,deadline)
                if len(dimensions)!=2 or any(not math.isfinite(v) for v in dimensions) or max(abs(a-b) for a,b in zip(dimensions,page_size))>1e-4:
                    raise Refused('page_dimensions_differ')
                files.append((label,snapshot,index))
            for dpi in DPIS:
                images=[]
                try:
                    for label,path,index in files:images.append(_raster(path,index,dpi,page_size,folder,label+str(dpi),deadline))
                    if not _outside_equal(images[1],images[2],rois,dpi/72):raise Refused('outside_roi_changed')
                    for i,roi in enumerate(rois):
                        deadline.remaining()
                        if not passed[i]:continue
                        box=tuple(int(v*dpi/72) for v in roi);crops=[im.crop(box) for im in images]
                        try:
                            old=metrics(crops[0],crops[1],dpi/72);new=metrics(crops[0],crops[2],dpi/72)
                            if any(new[key]>old[key]+EPSILON for key in old):passed[i]=False
                        except Refused as error:
                            # Local ink/background uncertainty disqualifies this
                            # ROI only. Grid/parser/resource errors remain global.
                            if str(error) not in {'dirty_border','no_ink','background_changed'}:raise
                            passed[i]=False
                        finally:
                            for crop in crops:crop.close()
                finally:
                    for image in images:image.close()
            deadline.remaining();return passed
    except (ValueError,TypeError,OSError,RuntimeError,subprocess.SubprocessError,ImportError):
        return None
