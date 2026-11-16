import numpy as np
from smartppt.consensus import overlapping_lines

def boxes():return [{'polygon':[[5,5],[25,5],[25,20],[5,20]]},{'polygon':[[5,21],[25,21],[25,40],[5,40]]}]

def test_only_truly_empty_light_intersection_can_be_recovered():
 image=np.full((50,40,3),255,dtype=np.uint8);image[10:13,10:20]=0;image[30:33,10:20]=0
 assert overlapping_lines(boxes())=={0,1}
 assert overlapping_lines(boxes(),image)==set()
 image[20,12]=0
 assert overlapping_lines(boxes(),image)=={0,1}

def test_tinted_paper_and_nonuniform_or_dark_overlap():
 image=np.full((50,40,3),(240,230,210),dtype=np.uint8)
 assert overlapping_lines(boxes(),image)==set()
 image[20,12]=(220,220,220)
 assert overlapping_lines(boxes(),image)=={0,1}
 image[:]=80
 assert overlapping_lines(boxes(),image)=={0,1}
