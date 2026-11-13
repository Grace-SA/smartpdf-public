from copy import deepcopy
from decimal import Decimal
import struct
import pytest
from smartppt.canvas_quantization import prove,Refused

def f32(v):return struct.unpack('f',struct.pack('f',float(v)))[0]
def meta(w,h):return {'media_box':['0','0',str(w),str(h)],'crop_box':['0','0',str(w),str(h)]}
def args():
 s=[f32('611.976'),f32('791.968')]
 return [[int(x*12700) for x in s],s,meta('611.976','791.968'),meta('611.971653543307','791.971653543307'),meta('611.971653543307','791.971653543307'),[(20.,20.,40.,40.)]]
def test_w9():
 a=args();b=deepcopy(a);r=prove(*a);assert a==b;assert a[0]==[7772095,10057993];assert r['pixel_grids']['432']==[3672,4752];assert not r['visual_acceptance']
@pytest.mark.parametrize('bad',[True,1.0,0,-1,2147483648,'7772095'])
def test_bad_emu(bad):
 a=args();a[0][0]=bad
 with pytest.raises(Refused):prove(*a)
def test_source_round_contract():
 a=args();a[0][1]=round(a[1][1]*12700)
 with pytest.raises(Refused,match='source_emu_contract'):prove(*a)
@pytest.mark.parametrize('key,value',[('media_box',['1','0','611.976','791.968']),('crop_box',['0','0','611','791']),('user_unit','2'),('rotation',90),('user_unit',True),('media_box',[0,0,611.976,791.968])])
def test_metadata(key,value):
 for i in [2,3,4]:
  a=args();a[i][key]=value
  with pytest.raises(Refused):prove(*a)
@pytest.mark.parametrize('delta',['0.000001','0.0000001','-0.000001'])
def test_output_shift(delta):
 a=args()
 for i in [3,4]:
  for key in ['media_box','crop_box']:a[i][key][2]=str(Decimal(a[i][key][2])+Decimal(delta))
 with pytest.raises(Refused,match='output_quantization_mismatch'):prove(*a)
def test_floor():
 a=args();a[3]=a[4]=meta('611.971654','791.943307')
 with pytest.raises(Refused,match='output_quantization_mismatch'):prove(*a)
def test_outputs_differ():
 a=args();a[3]=meta('611.971653','791.971654')
 with pytest.raises(Refused,match='output_dimensions_differ'):prove(*a)
@pytest.mark.parametrize('box',[(-1,1,3,3),(1,1,612,3),(1,1,3,792),(1,1,1,3),(1,1,float('nan'),3),(1,1,True,3),(611.97,20,611.975,30)])
def test_boxes(box):
 a=args();a[-1]=[box]
 with pytest.raises(Refused):prove(*a)
def test_grid_boundary():
 a=args();a[1]=[f32('612.001'),f32('792')];a[0]=[int(v*12700) for v in a[1]];a[2]=meta('612.001','792');a[3]=a[4]=meta('612','792')
 with pytest.raises(Refused,match='pixel_grid_mismatch'):prove(*a)
def test_parser():
 a=args();a[2]=meta('611.975','791.968')
 with pytest.raises(Refused,match='source_parser_disagreement'):prove(*a)

@pytest.mark.parametrize('emu,ticks',[(179,0),(180,1),(181,1),(539,1),(540,2),(541,2)])
def test_half_step(emu,ticks):
 from smartppt.canvas_quantization import _quantized_points
 from decimal import localcontext
 with localcontext() as context:
  context.prec=80
  assert _quantized_points(emu)==Decimal(ticks)*360/12700

def test_old_float_repr_six_places_is_not_raw_proof():
 a=args();a[3]=a[4]=meta('611.971654','791.971654')
 with pytest.raises(Refused,match='output_quantization_mismatch'):prove(*a)

@pytest.mark.parametrize('delta',['0.000000000001','-0.000000000001','0.0000000000001'])
def test_serialization_exact_boundary(delta):
 a=args()
 for i in [3,4]:
  for key in ['media_box','crop_box']:a[i][key][2]=str(Decimal(a[i][key][2])+Decimal(delta))
 with pytest.raises(Refused,match='output_quantization_mismatch'):prove(*a)

def test_sub_context_precision_source_crosses_pixel_boundary():
 a=args();a[0]=[5080000]*2;a[1]=[400.,400.]
 a[2]=meta('400.0000000000000000000000000001','400')
 a[3]=a[4]=meta('399.996850393701','399.996850393701')
 with pytest.raises(Refused,match='pixel_grid_mismatch'):prove(*a)

@pytest.mark.parametrize('precision',[2,6,12,28,100])
def test_global_decimal_context_cannot_change_proof(precision):
 from decimal import localcontext
 baseline=prove(*args())
 with localcontext() as context:
  context.prec=precision
  assert prove(*args())==baseline
  test_sub_context_precision_source_crosses_pixel_boundary()

def test_global_inexact_trap_does_not_drive_proof():
 from decimal import localcontext,Inexact,Rounded
 baseline=prove(*args())
 with localcontext() as context:
  context.prec=2;context.traps[Inexact]=True;context.traps[Rounded]=True
  assert prove(*args())==baseline
