import io,copy,re
import pdfplumber
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject,ArrayObject,NumberObject

def make(mode='normal'):
 w=PdfWriter();p=w.add_blank_page(width=612,height=792)
 font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Courier')})
 if mode=='badunicode':
  cmap=DecodedStreamObject();cmap.set_data(b'/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (A) /Ordering (B) /Supplement 0 >> def /CMapName /Bad def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 1 beginbfchar <31> <0037> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end')
  font[NameObject('/ToUnicode')]=w._add_object(cmap)
 p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
 rows=[['R'+str(r).zfill(2)]+[str(100+c)for c in range(1,8)]for r in range(16)]
 ops=['BT /F1 10 Tf 18 TL 1 0 0 1 40 740 Tm']
 if mode=='spacing':ops+=['0.1 Tc 0.2 Tw']
 for r,tokens in enumerate(rows):
  line='   '.join(tokens)
  if mode=='continuation'and r==12:
   a='   '.join(t if c not in(2,3,5)else' '*len(t)for c,t in enumerate(tokens));b='   '.join(t if c in(2,3,5)else' '*len(t)for c,t in enumerate(tokens))
   ops += [f'({a})'+(' Tj'if r==0 else" '"),f'({b})\n\''];continue
  if mode=='same-show-overlap'and r==12:
   ops+=['T* [('+line+') '+str(600*len(line))+' ('+line+')] TJ'];continue
  ops += [f'({line})'+(' Tj'if r==0 else" '")]
  if mode=='duplicate'and r==12:ops += ['0 0 Td ('+line+') Tj']
 ops+=['ET']
 if mode=='outside':ops += ["(oops) '"]
 if mode=='malformed':ops += ["BT 12 ' ET"]
 stream=DecodedStreamObject();stream.set_data('\n'.join(ops).encode());p[NameObject('/Contents')]=w._add_object(stream);buf=io.BytesIO();w.write(buf);data=buf.getvalue()
 # independently obtain each actual source token's box, then reproduce known model row-split.
 with pdfplumber.open(io.BytesIO(data))as doc:
  words=doc.pages[0].extract_words(x_tolerance=2,y_tolerance=2)
  cells=[]
  for r in range(16):
   for c,t in enumerate(rows[r]):
    # fixed monospaced columns, source baseline independently determines legitimate continuation
    candidates=[z for z in words if abs(z['x0']-(40+(37.2 if mode=='spacing'else 36)*c))<5 and abs(z['top']-(44.07+18*r+(18 if mode=='continuation'and(r>12 or(r==12 and c in(2,3,5)))else 0)))<4]
    if len(candidates)!=1:continue
    z=candidates[0];mr=r+(r>12)
    if r==12 and c in(2,3,5):mr=13
    cells.append(dict(r=mr,c=c,rs=1,cs=1,text=z['text'],sourceTextCandidate=[z['x0']-.1,z['top']-.1,z['x1']+.1,z['bottom']+.1]))
 return data,dict(widths=[36]*8,heights=[18]*17,cells=cells)

import io,sys,unittest,copy
import pdfplumber
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from layout_visible_row_merge import recover

class Tests(unittest.TestCase):
 def test_plain_and_spacing_consecutive_quotes(self):
  for mode in('normal','spacing'):
   with self.subTest(mode=mode):
    data,m=make(mode);self.assertEqual(len(m['cells']),128)
    for c in m['cells']:c['style']={'bold':c['c']==2,'font':'example','color':'001122'}
    original=copy.deepcopy(m)
    with pdfplumber.open(io.BytesIO(data))as d:o=recover(m,d.pages[0])
    self.assertEqual(m,original);self.assertEqual(len(o['heights']),16)
    from collections import Counter
    from layout_visible_row_merge import key
    self.assertEqual(Counter(key(c)for c in m['cells']),Counter(key(c)for c in o['cells']))
    self.assertEqual([c['r']for c in o['cells']],[c['r']-int(c['r']>12)for c in m['cells']])
    self.assertEqual(o['heights'],m['heights'][:12]+[sum(m['heights'][12:14])]+m['heights'][14:])
    self.assertEqual(o['widths'],m['widths'])
 def test_source_adversaries(self):
  for mode in('continuation','duplicate','same-show-overlap','badunicode','outside','malformed'):
   with self.subTest(mode=mode):
    data,m=make(mode);self.assertEqual(len(m['cells']),128)
    with pdfplumber.open(io.BytesIO(data))as d:self.assertEqual(recover(m,d.pages[0]),m)
 def test_font_customization_declined(self):
  from pypdf import PdfReader,PdfWriter
  from pypdf.generic import NameObject,DictionaryObject,NumberObject,ArrayObject
  for mode in('encoding','widths','alias','type0','budget'):
   with self.subTest(mode=mode):
    data,m=make();w=PdfWriter();p=w.add_page(PdfReader(io.BytesIO(data)).pages[0]);fonts=p['/Resources']['/Font'];f=fonts['/F1']
    if mode=='encoding':f[NameObject('/Encoding')]=NameObject('/WinAnsiEncoding')
    if mode=='widths':f[NameObject('/Widths')]=ArrayObject([NumberObject(600)]*256)
    if mode=='alias':fonts[NameObject('/Alias')]=DictionaryObject(dict(f))
    if mode=='type0':fonts[NameObject('/Other')]=DictionaryObject({NameObject('/Subtype'):NameObject('/Type0')})
    if mode=='budget':
     for i in range(17):fonts[NameObject('/Extra'+str(i))]=DictionaryObject(dict(f))
    buf=io.BytesIO();w.write(buf)
    with pdfplumber.open(io.BytesIO(buf.getvalue()))as d:self.assertEqual(recover(m,d.pages[0]),m)
 def test_bounds_and_stream_failure(self):
  from unittest.mock import patch
  data,m=make()
  for span in(10**9,-1,True):
   altered=copy.deepcopy(m);altered['cells'][0]['rs']=span
   with pdfplumber.open(io.BytesIO(data))as d:self.assertEqual(recover(altered,d.pages[0]),altered)
  with pdfplumber.open(io.BytesIO(data))as d:
   page=d.pages[0];page.pdf.stream.seek(7)
   with patch('layout_visible_row_merge.Evidence',side_effect=ValueError('unsupported')):self.assertEqual(recover(m,page),m)
   self.assertEqual(page.pdf.stream.tell(),7)
   out=recover(m,page);self.assertEqual(len(out['heights']),16);self.assertEqual(page.pdf.stream.tell(),7)
 def test_painting_and_ambiguous_owners(self):
  from pypdf import PdfReader,PdfWriter
  from pypdf.generic import ContentStream,NameObject,FloatObject,DictionaryObject
  for mode in('cover','alpha','clip','owner','wrong-geometry'):
   with self.subTest(mode=mode):
    data,m=make();w=PdfWriter();p=w.add_page(PdfReader(io.BytesIO(data)).pages[0]);cs=ContentStream(p.get_contents(),w);ops=list(cs.operations)
    if mode=='cover':ops += [([],b'q'),([FloatObject(1)]*3,b'rg'),([FloatObject(v)for v in(40,510,300,20)],b're'),([],b'f'),([],b'Q')]
    if mode=='clip':ops[:0]=[([FloatObject(v)for v in(0,0,100,100)],b're'),([],b'W'),([],b'n')]
    if mode=='alpha':
     p['/Resources'][NameObject('/ExtGState')]=DictionaryObject({NameObject('/A'):DictionaryObject({NameObject('/ca'):FloatObject(.5)})});ops.insert(0,([NameObject('/A')],b'gs'))
    if mode=='owner':
     t=next(c for c in m['cells']if c['r']==13);next(c for c in m['cells']if c['r']==3 and c['c']==t['c'])['sourceTextCandidate']=t['sourceTextCandidate'][:]
    if mode=='wrong-geometry':
     for c in m['cells']:
      if c['r']==13:c['sourceTextCandidate'][1]-=18;c['sourceTextCandidate'][3]-=18
    cs.operations=ops;p[NameObject('/Contents')]=w._add_object(cs);buf=io.BytesIO();w.write(buf)
    with pdfplumber.open(io.BytesIO(buf.getvalue()))as d:self.assertEqual(recover(m,d.pages[0]),m)
if __name__=='__main__':unittest.main()
