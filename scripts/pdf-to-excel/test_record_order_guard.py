import io,json,sys,tempfile,unittest,copy
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,ArrayObject,DictionaryObject,NumberObject,FloatObject,DecodedStreamObject
import pdfplumber
from layout_record_order_guard import verify,NOTICE
from layout_tables import LayoutError
from source_record_evidence import Evidence,color_space

class RecordOrder(unittest.TestCase):
 def fixture(self,mode='plain',named=False):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);path=Path(tmp.name)/'case.pdf';c=canvas.Canvas(str(path),pagesize=(612,400));c.setFont('Helvetica',10)
  labels=['Population group '+n+' people'for n in['Alpha','Bravo','Charlie','Delta','Echo']];rights=['A corresponding annual growth rate of '+v+'%'for v in['0.1','0.6','1.3','0.6','2.5']]
  if mode=='clip':
   p=c.beginPath();p.rect(0,0,1,1);c.clipPath(p,stroke=0)
  if mode=='alpha':c.setFillAlpha(0)
  if mode=='overprint':c.setFillOverprint(True)
  if mode=='form':c.beginForm('rows',0,0,612,400);c.setFont('Helvetica',10)
  for i,(left,right)in enumerate(zip(labels,rights)):
   y=310-i*12;rightx=570-stringWidth(right,'Helvetica',10);gap=rightx-40-stringWidth(left,'Helvetica',10)
   op=f'BT /F1 10 Tf 1 0 0 1 40 {y} Tm [({left}) {-gap*100} ({right})] TJ ET';c._code.append(op)
   if mode=='duplicate'and i==0:c._code.append(op)
  if mode=='form':c.endForm();c.doForm('rows')
  if mode=='cover':c.setFillColorRGB(1,1,1);c.rect(30,280,550,12,fill=1,stroke=0)
  c.save()
  if named:
   reader=PdfReader(path);writer=PdfWriter();p=writer.add_page(reader.pages[0]);f=DictionaryObject({NameObject('/FunctionType'):NumberObject(2),NameObject('/Domain'):ArrayObject([NumberObject(0),NumberObject(1)]),NameObject('/C0'):ArrayObject([NumberObject(1)]*3),NameObject('/C1'):ArrayObject([NumberObject(0)]*3),NameObject('/N'):NumberObject(1)})
   p['/Resources'][NameObject('/ColorSpace')]=DictionaryObject({NameObject('/Ink'):ArrayObject([NameObject('/Separation'),NameObject('/AnyInkName'),NameObject('/DeviceRGB'),f])})
   cs=p.get_contents();cs.operations.insert(0,([NameObject('/Ink')],b'cs'));cs.operations.insert(1,([NumberObject(1)],b'scn'));p.replace_contents(cs);writer.write(path)
  order=labels[1:]+labels[:1];text='All observed demographic and economic assumptions: '+' '.join(order)
  model=dict(widths=[270,270],heights=[16]*7,bbox=[30,65,580,200],method='layout',cells=[dict(r=0,c=0,rs=1,cs=1,text='Variable'),dict(r=0,c=1,rs=1,cs=1,text='Assumption'),dict(r=1,c=0,rs=1,cs=1,text=text,sourceTextCandidate=[30,70,300,150]),dict(r=1,c=1,rs=1,cs=1,text=' '.join(rights),sourceTextCandidate=[300,70,580,150]),dict(r=2,c=0,rs=1,cs=1,text='Other')])
  return path,model,labels
 def test_reordered_records_refused_and_immutable(self):
  for named in[False,True]:
   path,m,_=self.fixture(named=named);before=copy.deepcopy(m);data=path.read_bytes()
   with pdfplumber.open(path)as p:
    with self.assertRaisesRegex(LayoutError,'reordered'):verify(m,p.pages[0])
   self.assertEqual(m,before);self.assertEqual(path.read_bytes(),data)
 def test_existing_order_is_not_a_conflict(self):
  path,m,labels=self.fixture();m['cells'][2]['text']='All observed demographic and economic assumptions: '+' '.join(labels)
  with pdfplumber.open(path)as p:verify(m,p.pages[0])
 def test_no_native_reconstruction_on_hidden_or_unsupported(self):
  for mode in['cover','clip','alpha','overprint','form','duplicate']:
   path,m,_=self.fixture(mode)
   with self.subTest(mode=mode),pdfplumber.open(path)as p:verify(m,p.pages[0])
 def test_ambiguous_model_owner_declines(self):
  path,m,_=self.fixture();other=copy.deepcopy(m['cells'][2]);other['r']=3;m['cells'].append(other)
  with pdfplumber.open(path)as p:verify(m,p.pages[0])
 def test_normal_individual_records_decline(self):
  path,m,labels=self.fixture();m['cells']=[]
  for i,left in enumerate(labels):
   m['cells']+=[dict(r=i,c=0,rs=1,cs=1,text=left),dict(r=i,c=1,rs=1,cs=1,text='Annual growth rate of 0.1%')]
  with pdfplumber.open(path)as p:verify(m,p.pages[0])
 def test_target_budget(self):
  path,_,_=self.fixture()
  with pdfplumber.open(path)as p:
   e=Evidence(p.pages[0])
   for _ in range(6):self.assertTrue(e.visible(0))
   self.assertEqual(e.calls,1)
   e.calls=6
   with self.assertRaisesRegex(ValueError,'budget'):e.visible(1)
 def test_color_space_declines_complex_tints(self):
  f=DictionaryObject({NameObject('/FunctionType'):NumberObject(2),NameObject('/Domain'):ArrayObject([NumberObject(0),NumberObject(1)]),NameObject('/C0'):ArrayObject([NumberObject(1)]*3),NameObject('/C1'):ArrayObject([NumberObject(0)]*3),NameObject('/N'):NumberObject(1)})
  base=ArrayObject([NameObject('/Separation'),NameObject('/NotSpecialCased'),NameObject('/DeviceRGB'),f]);self.assertTrue(color_space(base))
  for key,val in[('/FunctionType',NumberObject(4)),('/N',NumberObject(0)),('/Range',ArrayObject([NumberObject(0),NumberObject(2)]*3))]:
   bad=copy.deepcopy(base);bad[3][NameObject(key)]=val;self.assertFalse(color_space(bad))

class AdditionalRecordTests(unittest.TestCase):
 fixture=RecordOrder.fixture
 def test_wrong_or_competing_right_owners_decline(self):
  for mode in['wrong','competing','cross-column','missing-occurrence']:
   path,m,_=self.fixture()
   if mode=='wrong':m['cells'][3]['sourceTextCandidate']=[0,200,300,350]
   elif mode in('competing','cross-column'):
    other=copy.deepcopy(m['cells'][3]);other['r']=4
    if mode=='cross-column':other['c']=0;other['cs']=2
    m['cells'].append(other)
   else:
    t=m['cells'][3]['text'];phrase='A corresponding annual growth rate of 0.6%';m['cells'][3]['text']=t.replace(phrase,'',1)
   with self.subTest(mode=mode),pdfplumber.open(path)as p:verify(m,p.pages[0])
 def test_left_geometry_competition_declines_even_without_same_text(self):
  for text in['Other','']:
   path,m,_=self.fixture();m['cells'][-1]['text']=text;m['cells'][-1]['sourceTextCandidate']=m['cells'][2]['sourceTextCandidate'][:]
   with self.subTest(text=text),pdfplumber.open(path)as doc:verify(m,doc.pages[0])
 def test_icc_color_profile_bounds_and_valid_named_ink(self):
  from PIL import ImageCms
  path,m,_=self.fixture(named=True);r=PdfReader(path);w=PdfWriter();page=w.add_page(r.pages[0]);space=page['/Resources']['/ColorSpace']['/Ink'];profile=DecodedStreamObject();blob=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes();profile.set_data(blob);profile[NameObject('/N')]=NumberObject(3);space[2]=ArrayObject([NameObject('/ICCBased'),w._add_object(profile)]);w.write(path)
  with pdfplumber.open(path)as p:
   self.assertEqual(p.pages[0].chars[0]['ncs'],'Separation')
   with self.assertRaises(LayoutError):verify(m,p.pages[0])
  for b in[blob[:128],b'\x00\x00\x00\x00'+blob[4:],blob[:128]+(5000).to_bytes(4,'big')+blob[132:]]:
   bad=copy.deepcopy(space);ps=DecodedStreamObject();ps.set_data(b);ps[NameObject('/N')]=NumberObject(3);bad[2]=ArrayObject([NameObject('/ICCBased'),ps]);self.assertFalse(color_space(bad))
 def test_reverse_ink_is_contribution_not_a_recovery_certificate(self):
  path,m,_=self.fixture();r=PdfReader(path);w=PdfWriter();p=w.add_page(r.pages[0]);cs=p.get_contents();prefix=[([NumberObject(0)],b'g'),([NumberObject(0),NumberObject(0),NumberObject(612),NumberObject(400)],b're'),([],b'f'),([NumberObject(1)],b'g')];cs.operations=prefix+cs.operations;p.replace_contents(cs);w.write(path)
  with pdfplumber.open(path)as doc:
   with self.assertRaises(LayoutError):verify(m,doc.pages[0])
 def test_page_stream_position_is_restored(self):
  for conflict in[False,True]:
   path,m,labels=self.fixture()
   if not conflict:m['cells'][2]['text']='All observed demographic and economic assumptions: '+' '.join(labels)
   with pdfplumber.open(path)as doc:
    page=doc.pages[0];_=page.chars;before=doc.stream.tell()
    if conflict:
     with self.assertRaises(LayoutError):verify(m,page)
    else:verify(m,page)
    self.assertEqual(doc.stream.tell(),before)
 def test_copy_pixel_mismatch_declines(self):
  import numpy as np
  path,m,_=self.fixture()
  with pdfplumber.open(path)as doc,patch.object(Evidence,'render',return_value=np.zeros((800,1224,3),dtype=np.uint8)):verify(m,doc.pages[0])
 def test_raw_show_identity_mismatch_declines(self):
  from source_record_evidence import Capture
  old=Capture.render_string
  def altered(self,*a,**kw):
   result=old(self,*a,**kw);self.shows[-1]['raw']=['00'];return result
  path,m,_=self.fixture()
  with pdfplumber.open(path)as doc,patch.object(Capture,'render_string',altered):verify(m,doc.pages[0])

if __name__=='__main__':unittest.main()
