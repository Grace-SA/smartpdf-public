import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).parent/'engine'))
import ocr_missing_digits as missing
import second_ocr

class Reader:
 def __init__(self,text='3'):self.text=text;self.calls=0
 def text_rec(self,crops):self.calls+=1;return [(self.text,.999)]*len(crops),None

class Tests(unittest.TestCase):
 def setUp(self):
  ctx=second_ocr.research_job();ctx.__enter__();self.addCleanup(ctx.__exit__,None,None,None)
 def fixture(self):
  im=np.full((180,180,3),255,np.uint8);h=np.zeros((180,180),np.uint8);v=h.copy()
  for x in (20,100,160):cv2.line(im,(x,20),(x,140),(0,0,0));cv2.line(v,(x,20),(x,140),255)
  for y in (20,60,100,140):cv2.line(im,(20,y),(160,y),(0,0,0));cv2.line(h,(20,y),(160,y),255)
  from digit_fixture import digit_image
  digit=digit_image()
  for y in (28,68,108):im[y:y+digit.shape[0],40:40+digit.shape[1]]=digit
  entries=[dict(r=r,c=0,rs=1,cs=1,text='3'if r<2 else '',confidence=.999)for r in range(3)]
  boxes=[(20,20+r*40,100,60+r*40)for r in range(3)]
  return im,entries,boxes,(h,v)
 def run_case(self,im,es,bs,masks,reader=None):
  return missing.recover(im,es,bs,reader or Reader(),2,dict(pixels=0,candidates=0),masks)
 def test_exact_evidence_recovers_only_empty(self):
  im,e,b,m=self.fixture();original=copy.deepcopy(e)
  with patch('second_ocr.recognize',return_value=[('3',96.6)]):out,n=self.run_case(im,e,b,m)
  self.assertEqual(n,1);self.assertEqual(out[2]['text'],'3');self.assertEqual(out[:2],original[:2]);self.assertEqual(e,original)
 def test_gray_difference_even_when_binary_same(self):
  im,e,b,m=self.fixture();region=im[108:126,40:54];region[region==0]=20
  out,n=self.run_case(im,e,b,m);self.assertEqual(n,0);self.assertEqual(out,e)
 def test_partial_glyph_and_cover(self):
  for area in ((108,126,48,54),(100,140,21,99)):
   im,e,b,m=self.fixture();y0,y1,x0,x1=area;im[y0:y1,x0:x1]=255
   out,n=self.run_case(im,e,b,m);self.assertEqual(n,0)
 def test_missing_rule_and_duplicate_geometry(self):
  im,e,b,m=self.fixture();m[0][140,30:90]=0
  self.assertEqual(self.run_case(im,e,b,m)[1],0)
  im,e,b,m=self.fixture();b[1]=b[2];self.assertEqual(self.run_case(im,e,b,m)[1],0)
 def test_conflicting_references_and_insufficient_support(self):
  im,e,b,m=self.fixture();e[1]['text']='8';self.assertEqual(self.run_case(im,e,b,m)[1],0)
  im,e,b,m=self.fixture();e[1]['confidence']=.5;self.assertEqual(self.run_case(im,e,b,m)[1],0)
 def test_second_reader_missing_or_disagrees_keeps_original(self):
  for answer in (None,[],[('8',99)],[('3',float('nan'))],[('3',float('inf'))],[('3',101)]):
   im,e,b,m=self.fixture()
   with patch('second_ocr.recognize',return_value=answer):out,n=self.run_case(im,e,b,m)
   self.assertEqual(n,0);self.assertEqual(out,e)
 def test_existing_value_and_merged_cell_untouched(self):
  im,e,b,m=self.fixture();e[2]['text']='9';self.assertEqual(self.run_case(im,e,b,m)[0],e)
  im,e,b,m=self.fixture();e[2]['rs']=2;self.assertEqual(self.run_case(im,e,b,m)[1],0)
 def test_extra_inner_edge_ink_declines(self):
  for axis,coordinate in [('x',21),('x',22),('x',97),('x',98),('x',99),('y',101),('y',102),('y',137),('y',138),('y',139)]:
   with self.subTest(axis=axis,coordinate=coordinate):
    im,e,b,m=self.fixture()
    if axis=='x':im[127:130,coordinate]=0
    else:im[coordinate,75:78]=0
    out,n=self.run_case(im,e,b,m);self.assertEqual(n,0);self.assertEqual(out,e)
 def test_primary_retry_failure_declines(self):
  im,e,b,m=self.fixture()
  with patch.object(Reader,'text_rec',side_effect=RuntimeError('failed')):out,n=self.run_case(im,e,b,m)
  self.assertEqual(n,0);self.assertEqual(out,e)
 def test_real_second_reader_blocks_systematic_primary_error(self):
  ctx=second_ocr.research_job();ctx.__enter__();self.addCleanup(ctx.__exit__,None,None,None)
  im,e,b,m=self.fixture();e[0]['text']=e[1]['text']='8'
  out,n=self.run_case(im,e,b,m,Reader('8'));self.assertEqual(n,0);self.assertEqual(out,e)
 def test_real_second_reader_matches_source_digit(self):
  ctx=second_ocr.research_job();ctx.__enter__();self.addCleanup(ctx.__exit__,None,None,None)
  im,e,b,m=self.fixture();out,n=self.run_case(im,e,b,m)
  self.assertEqual(n,1);self.assertEqual(out[2]['text'],'3')
if __name__=='__main__':unittest.main()
