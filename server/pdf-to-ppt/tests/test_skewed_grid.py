import math
from copy import deepcopy
import pytest
from smartppt.consensus import simple_grid_agreement

def grid(angle):
 cells=[['North','123.45','12.5%'],['South','678.90','9.8%']];lines=[];c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
 for row,texts in enumerate(cells):
  for col,text in enumerate(texts):
   x,y=100+400*col,200+100*row
   lines.append({'text':text,'polygon':[[px*c-py*s,px*s+py*c] for px,py in [(x,y),(x+100,y),(x+100,y+30),(x,y+30)]]})
 html='<table>'+''.join('<tr>'+''.join('<td>'+text+'</td>' for text in row)+'</tr>' for row in cells)+'</table>'
 return html,lines

@pytest.mark.parametrize('angle',[-3,-1.4,0,1.4,3])
def test_skew_preserves_strict_cell_text_and_aligned_rows(angle):
 html,lines=grid(angle);original=deepcopy(lines)
 assert simple_grid_agreement(html,lines,list(range(6)))
 assert lines==original
 wrong=deepcopy(lines);wrong[1]['text'],wrong[4]['text']=wrong[4]['text'],wrong[1]['text']
 assert not simple_grid_agreement(html,wrong,list(range(6)))

def test_skew_does_not_hide_displaced_or_inconsistently_rotated_cells():
 html,lines=grid(1.4)
 for p in lines[1]['polygon']:p[1]+=30
 assert not simple_grid_agreement(html,lines,list(range(6)))
 html,lines=grid(0);lines[1]['polygon'][1][1]+=20
 assert not simple_grid_agreement(html,lines,list(range(6)))
 html,lines=grid(10)
 assert not simple_grid_agreement(html,lines,list(range(6)))
