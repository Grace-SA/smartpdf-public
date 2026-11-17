from copy import deepcopy
import numpy as np
from smartppt.ocr_bounds import trim_line_padding
from smartppt.consensus import overlapping_lines,erase_bounds

def lines():return [{'polygon':[[10,10],[150,10],[150,53],[10,53]]},{'polygon':[[10,28],[150,28],[150,70],[10,70]]}]

def test_padding_is_trimmed_only_in_full_width_empty_gutter():
 image=np.full((90,170,3),255,dtype=np.uint8);image[20:30,20:140]=0;image[47:57,20:140]=0;raw=lines();prior=deepcopy(raw)
 assert overlapping_lines(raw,image)=={0,1}
 refined,changed=trim_line_padding(image,raw)
 assert changed==[0,1] and raw==prior
 assert overlapping_lines(refined,image)==set()
 first,second=map(erase_bounds,refined)
 assert first[1]<=20 and first[3]>=30 and first[3]<=47
 assert second[1]>=30 and second[1]<=47 and second[3]>=57

def test_no_gutter_or_slanted_detection_never_guesses_a_cut():
 image=np.full((90,170,3),255,dtype=np.uint8);image[10:71,80]=0
 assert trim_line_padding(image,lines())==(lines(),[])
 image[:]=255;raw=lines();raw[0]['polygon'][1][1]+=4
 assert trim_line_padding(image,raw)==(raw,[])
