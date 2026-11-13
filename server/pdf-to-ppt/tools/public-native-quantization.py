"""Offline canvas-quantization diagnosis, NOT conversion acceptance.

Default production guards are unchanged. This proves one explicit EMU-to-mm100
model before inspecting fixed-coordinate pixels; it never edits, crops, rescales
or registers a PDF/image. Even successful diagnostics do not authorize recovery.
"""
import argparse,json,math,os,subprocess,sys,tempfile,struct
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from smartppt import light_visual_guard as guard
from smartppt.canvas_quantization import prove
MAX_METADATA=65536

# Raw PDF numbers are serialized as decimal strings, never through float. Run
# parsers in a bounded child against immutable snapshots, not caller paths.
_PARSE=r'''import sys,json,zipfile,re
from pypdf import PdfReader
from decimal import Decimal
import pypdf.generic._base as base
OriginalFloat=base.FloatObject
class RawFloat(OriginalFloat):
 def __new__(cls,value='0.0',context=None):
  if not isinstance(value,(bytes,str)):raise ValueError('raw_float_token_required')
  token=value.decode('ascii') if isinstance(value,bytes) else value
  if len(token)>64 or not re.fullmatch(r'[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)',token):raise ValueError('invalid_pdf_decimal_token')
  exact=Decimal(token)
  if not exact.is_finite():raise ValueError('nonfinite_pdf_number')
  result=super().__new__(cls,token);result.raw_decimal=token;return result
base.FloatObject=RawFloat
import pypdf.generic._data_structures as structures
structures.FloatObject=RawFloat
from io import BytesIO
probe=base.NumberObject.read_from_stream(BytesIO(b'1.00000000000000001 '))
if not isinstance(probe,RawFloat) or probe.raw_decimal!='1.00000000000000001':raise ValueError('pdf_numeric_hook_unavailable')
probe=structures.read_object(BytesIO(b'1.00000000000000001 '),None)
if not isinstance(probe,RawFloat) or probe.raw_decimal!='1.00000000000000001':raise ValueError('pdf_numeric_fast_hook_unavailable')
# Both parser number paths resolve these child-local module globals.
# No parent interpreter state is changed; never serialize float approximations.
def number(value):
 value=value.get_object() if hasattr(value,'get_object') else value
 if isinstance(value,RawFloat):return value.raw_decimal
 if isinstance(value,int) and not isinstance(value,bool):return str(value)
 raise ValueError('unproven_pdf_number')
def box(value):
 value=value.get_object() if hasattr(value,'get_object') else value
 return [number(x) for x in value]
from xml.etree import ElementTree
index=int(sys.argv[1]);result=[]
for path in sys.argv[2:5]:
 reader=PdfReader(path,strict=True)
 if reader.is_encrypted or not 0<=index<len(reader.pages)<=200:raise ValueError('unsupported_pdf')
 page=reader.pages[index]
 media=page.get('/MediaBox');crop=page.get('/CropBox',media)
 result.append(dict(media_box=box(media),crop_box=box(crop),user_unit=number(page.get('/UserUnit',1)),rotation=number(page.get('/Rotate',0))))
with zipfile.ZipFile(sys.argv[5]) as z:
 entries=z.infolist()
 if len(entries)>10000:raise ValueError('zip_entry_limit')
 matches=[x for x in entries if x.filename=='ppt/presentation.xml']
 if len(matches)!=1 or matches[0].file_size>262144 or matches[0].flag_bits&1:raise ValueError('presentation_xml_limit')
 with z.open(matches[0]) as stream:raw=stream.read(262145)
 if len(raw)>262144:raise ValueError('unsafe_xml')
 text=raw.decode('utf-8-sig')
 if '\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('unsafe_xml')
 root=ElementTree.fromstring(text);sizes=root.findall('{http://schemas.openxmlformats.org/presentationml/2006/main}sldSz')
 if len(sizes)!=1:raise ValueError('slide_size_count')
 values=[sizes[0].get(k,'') for k in ('cx','cy')]
 if any(not v.isascii() or not v.isdecimal() or len(v)>12 for v in values):raise ValueError('invalid_slide_size')
 emu=[int(v) for v in values]
print(json.dumps(dict(pages=result,emu=emu)))
'''

def _limits():
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_METADATA,MAX_METADATA))
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))


def raw_metadata(files,presentation,index,folder,deadline):
    output=folder/'raw-metadata.json'
    with output.open('xb') as stream,(folder/'raw-metadata.stderr').open('xb') as errors:
        subprocess.run([sys.executable,'-c',_PARSE,str(index),*[str(p) for p in files],str(presentation)],
                       stdout=stream,stderr=errors,check=True,timeout=min(30,deadline.remaining()),preexec_fn=_limits)
    deadline.remaining()
    if output.stat().st_size>MAX_METADATA:raise ValueError('metadata_limit')
    return json.loads(output.read_text())


def diagnose(source,previous,candidate,presentation,page,source_boxes,*,timeout=120):
    result={'diagnostic_only':True,'production_acceptance':False,'geometry_proven':False,'samples':[]}
    try:
        if type(page) is not int or not 1<=page<=200:raise ValueError('invalid_page')
        if os.name!='posix':raise ValueError('posix_required')
        deadline=guard.Deadline(timeout);index=page-1
        with tempfile.TemporaryDirectory(prefix='smartppt-canvas-diagnostic-') as temp:
            folder=Path(temp);files=[];sizes=[]
            for label,path in [('source',source),('previous',previous),('candidate',candidate)]:
                snapshot=guard._snapshot(Path(path),folder/(label+'.pdf'),deadline);files.append(snapshot)
                sizes.append(guard._metadata(snapshot,index,folder,label,deadline))
            pptx=guard._snapshot(Path(presentation),folder/'presentation.pptx',deadline)
            raw=raw_metadata(files,pptx,index,folder,deadline)
            proof=prove(raw['emu'],sizes[0],*raw['pages'],source_boxes)
            expected_observed=tuple(struct.unpack('f',struct.pack('f',float(v)))[0] for v in proof['serialized_output_size'])
            if any(tuple(size)!=expected_observed for size in sizes[1:]):
                raise ValueError('output_parser_disagreement')
            # Independently demand all actual PDFium dimensions and every actual
            # Poppler PNG grid agree with the source's fixed grid, without resize.
            for size in sizes:
                if any(tuple(math.ceil(v*d/72) for v in size)!=tuple(math.ceil(v*d/72) for v in sizes[0]) for d in guard.DPIS):
                    raise ValueError('pdfium_pixel_grid_mismatch')
            rois=guard._rois(sizes[0],source_boxes)
            # _rois expands ink bounds to an integer-point crop. Validate that
            # entire crop against raw source AND quantized output, not merely
            # its original ink box or the rounded-up PNG dimensions.
            physical_sizes=[proof['source_size'],proof['serialized_output_size']]
            for width,height in physical_sizes:
                w,h=Decimal(width),Decimal(height)
                if any(not (0<=l<r<=w and 0<=t<b<=h) for l,t,r,b in rois):
                    raise ValueError('expanded_roi_outside_page')
            result.update(geometry_proven=True,geometry_proof=proof)
            passed=[True]*len(rois)
            for dpi in guard.DPIS:
                images=[]
                try:
                    for label,path in zip(('source','previous','candidate'),files):
                        images.append(guard._raster(path,index,dpi,sizes[0],folder,label+str(dpi),deadline))
                    if not guard._outside_equal(images[1],images[2],rois,dpi/72):raise ValueError('outside_roi_changed')
                    for i,roi in enumerate(rois):
                        deadline.remaining();box=tuple(int(v*dpi/72) for v in roi);crops=[im.crop(box) for im in images]
                        sample={'dpi':dpi,'roi':i,'nonregressing':False}
                        try:
                            old=guard.metrics(crops[0],crops[1],dpi/72);new=guard.metrics(crops[0],crops[2],dpi/72)
                            sample.update(previous=old,candidate=new,nonregressing=all(new[k]<=old[k]+guard.EPSILON for k in old))
                        except guard.Refused as error:sample['reason']=str(error)
                        finally:
                            for crop in crops:crop.close()
                        passed[i]&=sample['nonregressing'];result['samples'].append(sample)
                finally:
                    for image in images:image.close()
            deadline.remaining();result.update(nonregressing_rois=passed,all_visual_nonregressing=all(passed))
    except (ValueError,TypeError,OSError,RuntimeError,subprocess.SubprocessError,ImportError) as error:
        result['reason']=str(error) or type(error).__name__
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','previous','candidate','presentation'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--page',type=int,required=True,help='One-based page in all three PDFs')
    parser.add_argument('--boxes',required=True,help='JSON array of verified lower-left source ink boxes; this tool does not prove text ownership')
    parser.add_argument('--timeout',type=float,default=120)
    args=parser.parse_args()
    if len(args.boxes)>MAX_METADATA:parser.error('boxes input too large')
    boxes=json.loads(args.boxes)
    print(json.dumps(diagnose(args.source,args.previous,args.candidate,args.presentation,args.page,boxes,timeout=args.timeout),indent=2))

if __name__=='__main__':main()
