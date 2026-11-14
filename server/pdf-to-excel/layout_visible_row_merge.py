"""Coalesce complementary model rows only with visible standard-Courier evidence.

Preserve every existing nonempty field; never decode new output text. Unsupported
fonts, painting, ambiguous geometry, or exceeded budgets leave the model intact."""
import io,copy,re,math
from collections import Counter
import numpy as np,pdfplumber
from pypdf import PdfReader,PdfWriter
from pypdf.generic import ContentStream,NameObject,TextStringObject,ByteStringObject
from source_record_evidence import Evidence
from source_hidden_ocr import resolve,read_operations

def compact(t):return ''.join(t.split())
def box(b):return isinstance(b,(list,tuple))and len(b)==4 and all(isinstance(v,(int,float))and math.isfinite(v)for v in b)and b[0]<b[2]and b[1]<b[3]
def key(c):return repr(sorted((k,v)for k,v in c.items()if k!='r'))
def _recover(m,page):
 cols=len(m['widths']);rows=len(m['heights']);cells=m['cells']
 if not 5<=cols<=16 or not 12<=rows<=100 or len(cells)>1600:return m
 if any(type(c.get(k))is not int for c in cells for k in ('r','c','rs','cs')):return m
 if any(not(0<=c['r']<c['r']+c['rs']<=rows and 0<=c['c']<c['c']+c['cs']<=cols)or not isinstance(c.get('text'),str)or len(c['text'])>2000 for c in cells):return m
 if any(not isinstance(v,(int,float))or not math.isfinite(v)or v<=0 for v in m['widths']+m['heights']):return m
 occupied={}
 for c in cells:
  if c['rs']!=1 or c['cs']!=1:
   if c['r']>=2:return m
  for r in range(c['r'],c['r']+c['rs']):
   for col in range(c['c'],c['c']+c['cs']):
    if (r,col)in occupied:return m
    occupied[r,col]=c
 candidates=[]
 for r in range(3,rows-2):
  a=[c for c in cells if c['r']==r and c['text'].strip()];b=[c for c in cells if c['r']==r+1 and c['text'].strip()]
  if not a or not b or not any(c['c']==0 for c in a)or any(c['c']==0 for c in b):continue
  pair=a+b
  if len(pair)!=cols or {c['c']for c in pair}!=set(range(cols))or any(c['rs']!=1 or c['cs']!=1 or not box(c.get('sourceTextCandidate'))for c in pair):continue
  if any(not re.fullmatch(r'\d[\d,.]*',c['text'].strip())for c in pair if c['c']):continue
  if sum(all((y,col)in occupied and occupied[y,col]['text'].strip()for col in range(cols))for y in range(2,r))<10:continue
  if not all((r+2,col)in occupied and occupied[r+2,col]['text'].strip()for col in range(cols)):continue
  candidates.append((r,pair))
 if len(candidates)!=1:return m
 r,pair=candidates[0]
 if any(set(c)-{'r','c','rs','cs','text','sourceTextCandidate'} for c in cells if c['r']in(r,r+1)and not c['text'].strip()):return m
 stream=page.pdf.stream;pos=stream.tell()
 try:
  reader=PdfReader(stream);source=reader.pages[page.page_number-1]
  raw=resolve(source.get('/Contents'));ops=read_operations(list(raw)if isinstance(raw,list)else[raw],reader,dict(bytes=0,streams=0,ops=0,forms=0))
  # No nontext painting or clipping: overlapping / partly covered glyphs are not a supported recovery subset.
  allowed={b'q',b'Q',b'cm',b'gs',b'rg',b'RG',b'g',b'G',b'k',b'K',b'BT',b'ET',b'Tf',b'Tc',b'Tw',b'Tz',b'TL',b'Tr',b'Ts',b'Td',b'TD',b'Tm',b'T*',b'Tj',b'TJ',b"'"}
  if any(o not in allowed for a,o in ops):return m
  # Recovery is confined to standard, unmodified Courier glyph encoding.
  # A ToUnicode map or custom font program cannot attest displayed digits.
  fonts=resolve(source['/Resources']['/Font'])
  if not isinstance(fonts,dict)or not 1<=len(fonts)<=16:return m
  courier=[resolve(f)for f in fonts.values()if resolve(f).get('/BaseFont')=='/Courier']
  if len(courier)!=1 or dict(courier[0])!={'/Type':'/Font','/Subtype':'/Type1','/BaseFont':'/Courier'}:return m
  for f in fonts.values():
   f=resolve(f)
   if f.get('/Subtype')not in('/Type1','/TrueType'):return m
   if f is not courier[0] and ('Courier'in str(f.get('/BaseFont',''))or 'Courier'in str(resolve(f.get('/FontDescriptor',{})).get('/FontName',''))):return m
  normalized=[];inside=False
  for a,o in ops:
   if o==b'BT':
    if inside:return m
    inside=True
   elif o==b'ET':
    if not inside:return m
    inside=False
   if o==b"'":
    if not inside or len(a)!=1 or not isinstance(a[0],(TextStringObject,ByteStringObject)):return m
    normalized.extend([([],b'T*'),(a,b'Tj')])
   else:normalized.append((a,o))
  if inside:return m
  w=PdfWriter();p=w.add_page(source);cs=ContentStream(None,w);cs.operations=normalized;p[NameObject('/Contents')]=w._add_object(cs);buf=io.BytesIO();w.write(buf)
  if buf.tell()>40_000_000:return m
 finally:stream.seek(pos)
 with pdfplumber.open(io.BytesIO(buf.getvalue()))as doc:
  p=doc.pages[0];e=Evidence(p)
  original=np.asarray(page.to_image(resolution=144).original.convert('RGB'))
  if not np.array_equal(original,e.render(buf.getvalue())):return m
  # Require full decoded glyph/position correspondence to the unchanged page.
  def glyphkey(c):return(c['text'],c.get('fontname'),c.get('matrix'),c.get('adv'),c.get('size'),*(round(c[k],5)for k in('x0','top','x1','bottom')))
  if Counter(map(glyphkey,page.chars))!=Counter(map(glyphkey,p.chars)):return m
  if len(page.chars)*len(pair)>2_000_000:return m
  target_chars=[c for c in page.chars if c['text'].strip()and any(b['sourceTextCandidate'][0]<=(c['x0']+c['x1'])/2<=b['sourceTextCandidate'][2]and b['sourceTextCandidate'][1]<=(c['top']+c['bottom'])/2<=b['sourceTextCandidate'][3]for b in pair)]
  if not target_chars or any(c.get('fontname')!='Courier'for c in target_chars):return m
  allglyphs=[g for s in e.shows for g in s['glyphs']if g['text'].strip()]
  matches=[];work=len(page.chars)*len(pair)
  for i,s in enumerate(e.shows):
   gs=[g for g in s['glyphs']if g['text'].strip()]
   if not gs or max(g['bbox'][1]for g in gs)-min(g['bbox'][1]for g in gs)>.01:continue
   if any(g['matrix'][1]or g['matrix'][2]or g['matrix'][0]<=0 or g['matrix'][3]<=0 for g in gs):continue
   by={id(c):[]for c in pair};ok=True
   work+=len(gs)*len(cells)
   if work>2_000_000:return m
   for g in gs:
    x=(g['bbox'][0]+g['bbox'][2])/2;y=p.height-(g['bbox'][1]+g['bbox'][3])/2
    owners=[c for c in cells if box(c.get('sourceTextCandidate'))and c['sourceTextCandidate'][0]<=x<=c['sourceTextCandidate'][2]and c['sourceTextCandidate'][1]<=y<=c['sourceTextCandidate'][3]]
    if len(owners)!=1 or id(owners[0])not in by:ok=False;break
    by[id(owners[0])].append(g)
   if not ok or any(compact(''.join(g['text']for g in by[id(c)]))!=compact(c['text'])for c in pair):continue
   ordered=sorted(pair,key=lambda c:c['c'])
   if any(max(g['bbox'][2]for g in by[id(a)])>=min(g['bbox'][0]for g in by[id(b)])for a,b in zip(ordered,ordered[1:])):continue
   ids={id(g)for g in gs}
   def overlaps(a,b):return max(a[0],b[0])+1e-7<min(a[2],b[2])and max(a[1],b[1])+1e-7<min(a[3],b[3])
   work+=len(gs)*len(allglyphs)
   if work>2_000_000:return m
   if any(overlaps(g['bbox'],h['bbox'])for g in gs for h in allglyphs if id(h)!=id(g)):continue
   if e.visible(i):matches.append(i)
  if len(matches)!=1:return m
 out=copy.deepcopy(m)
 # Empty generated cells can be discarded only where the complementary field occupies that slot.
 out['cells']=[c for c in out['cells']if not(c['r']in(r,r+1)and not c['text'].strip())]
 for c in out['cells']:
  if c['r']>r:c['r']-=1
 out['heights'][r]+=out['heights'].pop(r+1)
 if Counter(key(c)for c in cells if c['text'].strip())!=Counter(key(c)for c in out['cells']if c['text'].strip()):raise AssertionError('field conservation')
 return out


def recover(m,page):
 from pypdf.errors import PyPdfError
 from pdfminer.pdfexceptions import PDFException
 from pdfminer.psexceptions import PSException
 from pdfplumber.utils.exceptions import MalformedPDFException
 try:stream=page.pdf.stream;pos=stream.tell()
 except (AttributeError,OSError,ValueError):return m
 try:
  try:return _recover(m,page)
  except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,OSError,RuntimeError,PyPdfError,MalformedPDFException,PDFException,PSException):return m
 finally:stream.seek(pos)
