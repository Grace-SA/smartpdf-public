"""Narrow refusal of source-matched numeric fields with uniform final RGB regions.

This is not a visibility certificate. Nonuniform occlusion, unusual fonts and
unverifiable ownership are outside this detector; no values are recovered.
"""
import math,re
from collections import defaultdict
import numpy as np
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from pdfplumber.utils import extract_text
from pdfplumber.utils.exceptions import MalformedPDFException
from layout_native_order import _box,_geometry,_inside,_overlap,_finite
from layout_tables import visible_box,LayoutError
from layout_split_rows import black_glyph

NOTICE=('A numeric field could not be verified as visible on the final PDF page. '
        'Conversion was stopped rather than exporting potentially concealed content.')
_NUMBER=re.compile(r'[+\-]?[0-9][0-9.,]*%?\Z')
_STANDARD={'Helvetica','Helvetica-Bold','Helvetica-Oblique','Helvetica-BoldOblique',
 'Times-Roman','Times-Bold','Times-Italic','Times-BoldItalic','Courier','Courier-Bold',
 'Courier-Oblique','Courier-BoldOblique'}

def standard_fonts(page):
    stream=page.pdf.stream;position=stream.tell()
    try:
        reader=PdfReader(stream);p=reader.pages[page.page_number-1]
        if p.get('/UserUnit',1)!=1:return set()
        seen=set();fonts=set();count=0
        def walk(res,depth=0):
            nonlocal count
            if depth>8:raise ValueError('Form depth')
            if res is None:return
            res=res.get_object();key=id(res)
            if key in seen:raise ValueError('Repeated resource graph')
            seen.add(key);count+=1
            if count>32:raise ValueError('Resource budget')
            mapping=res.get('/Font',{}).get_object() if hasattr(res.get('/Font',{}),'get_object')else res.get('/Font',{})
            if len(mapping)>32:raise ValueError('Font budget')
            for obj in mapping.values():
                f=obj.get_object();name=str(f.get('/BaseFont','')).removeprefix('/')
                if (f.get('/Subtype')!='/Type1' or name not in _STANDARD
                    or len(f)>5 or set(f)-{'/Type','/Subtype','/BaseFont','/Encoding','/Name'}
                    or f.get('/Encoding') not in (None,'/WinAnsiEncoding','/StandardEncoding')):raise ValueError('Nonstandard font')
                fonts.add(name)
            xobjs=res.get('/XObject',{});xobjs=xobjs.get_object()if hasattr(xobjs,'get_object')else xobjs
            if len(xobjs)>32:raise ValueError('XObject budget')
            for obj in xobjs.values():
                x=obj.get_object()
                if x.get('/Subtype')=='/Form' and x.get('/Resources') is not None:walk(x['/Resources'],depth+1)
        walk(p.get('/Resources'));return fonts
    finally:stream.seek(position)

def verify(model,page):
    try:bad=_conflict(model,page)
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,OSError,RuntimeError,PyPdfError,MalformedPDFException):return
    if bad:raise LayoutError(NOTICE)

def _conflict(model,page):
    if page.rotation or tuple(page.bbox)!=(0,0,page.width,page.height) or tuple(page.cropbox)!=tuple(page.mediabox):return False
    if (not _finite(page.width)or not _finite(page.height)or min(page.width,page.height)<=0
        or math.ceil(page.width*3)*math.ceil(page.height*3)>20_000_000):return False
    if len(page.images)>64:return False
    image_pixels=0
    for image in page.images:
        size=image.get('srcsize')
        if not isinstance(size,(tuple,list))or len(size)!=2 or any(not _finite(v)or v<=0 for v in size):return False
        image_pixels+=size[0]*size[1]
        if image_pixels>20_000_000:return False
    cells=model['cells'];chars=[g for g in page.chars if g['text'].strip()]
    if not 1<=len(cells)<=2000 or not 1<=len(chars)<=20000 or len(cells)*len(chars)>2_000_000:return False
    if any(not _box(_geometry(g))for g in chars):return False
    owners=[]
    for c in cells:
        if not isinstance(c.get('text'),str)or not c['text'].strip():continue
        if not _box(c.get('sourceTextCandidate'))and c.get('sourceFont')is True and _box(c.get('sourceTextBox')):
            c=dict(c,sourceTextCandidate=c['sourceTextBox'])
        owners.append(c)
    if any(not _box(c.get('sourceTextCandidate'))for c in owners):return False
    candidates=[c for c in owners if 2<=len(c['text'])<=30 and _NUMBER.fullmatch(c['text'])]
    if not candidates:return False
    fonts=standard_fonts(page)
    if not fonts:return False
    images={};view=visible_box(page);work=0
    def owns(c,g):
        b=c['sourceTextCandidate'];return b[0]<=(g['x0']+g['x1'])/2<=b[2]and b[1]<=(g['top']+g['bottom'])/2<=b[3]
    for cell in candidates:
        gs=[g for g in chars if owns(cell,g)]
        work+=len(chars)+len(gs)*len(owners)+len(chars)
        if work>2_000_000:return False
        if not 2<=len(gs)<=60:continue
        if any(not black_glyph(g)or g.get('fontname')not in fonts or not g.get('upright')or not 6<=g['height']<=36 or g['x1']-g['x0']<1
            or len(g.get('matrix',()))!=6 or not all(_finite(v)for v in g['matrix'])
            or g['matrix'][0]<=0 or g['matrix'][3]<=0 or abs(g['matrix'][1])>.001 or abs(g['matrix'][2])>.001
            or any(o is not cell and owns(o,g)for o in owners)for g in gs):continue
        if len({g['fontname']for g in gs})!=1 or max(g['top']for g in gs)-min(g['top']for g in gs)>.1:continue
        # Exact coincident repeated shows can support a refusal, not reconstruction.
        unique=[]
        for g in gs:
            if not any(g['text']==h['text']and _geometry(g)==_geometry(h)for h in unique):unique.append(g)
        ordered=sorted(unique,key=lambda g:g['x0'])
        if any(a['x1']>b['x0']+.01 for a,b in zip(ordered,ordered[1:])):continue
        if ''.join(extract_text(ordered,x_tolerance=2,y_tolerance=3).split())!=cell['text']:continue
        h=max(g['height']for g in gs);pad=h*.5+1
        region=(min(g['x0']for g in gs)-pad,min(g['top']for g in gs)-pad,max(g['x1']for g in gs)+pad,max(g['bottom']for g in gs)+pad)
        if not _inside(region,view):continue
        ids={id(g)for g in gs}
        if any(id(g)not in ids and _overlap(_geometry(g),region)for g in chars):continue
        uniform=True
        for scale in (2,3):
            if scale not in images:images[scale]=np.asarray(page.to_image(resolution=72*scale,antialias=True).original.convert('RGB'))
            im=images[scale]
            expected=(math.ceil(page.height*scale),math.ceil(page.width*scale))
            if im.ndim!=3 or im.shape[2]!=3 or im.shape[:2]!=expected or im.shape[0]*im.shape[1]>20_000_000:return False
            sx=im.shape[1]/page.width;sy=im.shape[0]/page.height
            x0,y0,x1,y1=math.floor(region[0]*sx),math.floor(region[1]*sy),math.ceil(region[2]*sx),math.ceil(region[3]*sy)
            if not 0<=x0<x1<=im.shape[1]or not 0<=y0<y1<=im.shape[0]:uniform=False;break
            roi=im[y0:y1,x0:x1]
            if not np.all(roi==roi[0,0]):uniform=False;break
        if uniform:return True
    return False
