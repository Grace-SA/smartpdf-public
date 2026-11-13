from copy import deepcopy
import pytest
from smartppt.consensus import region_agreement

def evidence():
 lines=[{'text':text,'confidence':.99,'polygon':[[20,y],[200,y],[200,y+20],[20,y+20]]} for y,text in [(20,'Month 1 revenue 123.45'),(60,'Month 2 revenue 678.90'),(100,'Month 3 revenue -234.56')]]
 record={'input_sha256':'digest','image_size':[400,200],'lines':lines}
 parent={'label':'text','bbox':[10,10,210,130],'content':'\n'.join(l['text'] for l in lines)}
 children=[{'label':'text','bbox':[15,y-5,205,y+25],'content':line['text']} for y,line in zip([20,60,100],lines)]
 verifier={'input_sha256':'digest','image_size':[400,200],'coordinate_space':'pixels','capped':False,'blocks':[parent,*children]}
 return record,verifier

def test_paragraph_and_exact_nested_lines_are_consistent():
 record,verifier=evidence();assert region_agreement(record,verifier)==[True]*3
 # One missing child detection does not remove the parent model's exact line.
 del verifier['blocks'][2];assert region_agreement(record,verifier)==[True]*3

@pytest.mark.parametrize('change',['number','order','truncated','picture','table','crossing','uncontained'])
def test_nested_disagreement_or_structural_overlap_cannot_authorize_text(change):
 record,verifier=evidence()
 if change=='number':verifier['blocks'][2]['content']='Month 2 revenue 678.99'
 elif change=='order':verifier['blocks'][0]['content']='\n'.join(l['text'] for l in reversed(record['lines']))
 elif change=='truncated':verifier['blocks'][0]['content']=record['lines'][0]['text']+'\n'+record['lines'][1]['text']
 elif change in ('picture','table'):verifier['blocks'][2]['label']=change
 elif change=='crossing':verifier['blocks'][2]['bbox'][0]=5
 elif change=='uncontained':verifier['blocks'][2]['bbox'][2]=170
 result=region_agreement(record,verifier)
 assert result[1] is False
 if change in ('order','truncated'):assert result==[False]*3
 else:assert result==[True,False,True]
