"""Recover exact, unique, whole-token lines inside a mismatched OCR block."""
from difflib import SequenceMatcher
import unicodedata
from .quality import normalized
def cjk(c):return any(a<=ord(c)<=b for a,b in ((0x3400,0x9fff),(0x20000,0x323af)))

def partial_line_agreement(texts,content):
 lines=[normalized(s) for s in texts];actual=''.join(lines);reference=normalized(content);approved=[False]*len(lines)
 if not actual or max(len(actual),len(reference))>16000:return approved
 eligible={i for i,line in enumerate(lines) if len(line)>=8 and sum(c.isalpha() for c in line)>=2
           and actual.count(line)==reference.count(line)==1}
 if not eligible:return approved
 # Keep original word boundaries. NFKC combinations that cannot be mapped
 # unambiguously remain raster; never guess where a verifier token ends.
 expanded=unicodedata.normalize('NFKC',content);positions=[i for i,c in enumerate(expanded) if not c.isspace()]
 locations=[reference.find(line) for line in lines if line and actual.count(line)==reference.count(line)==1]
 if any(b<a for a,b in zip(locations,locations[1:])):return approved
 matcher=SequenceMatcher(None,actual,reference,autojunk=False);blocks=matcher.get_matching_blocks();edits=[op for op in matcher.get_opcodes() if op[0]!='equal'];start=0
 for n,line in enumerate(lines):
  end=start+len(line)
  if n in eligible:
   match=next((b for b in blocks if b.a<=start and end<=b.a+b.size),None)
   if match and not any((a==b and start<=a<=end) or (a<end and b>start) for _,a,b,_,_ in edits):
    first=match.b+start-match.a;last=first+len(line)-1
    prev=expanded[positions[first]-1] if positions[first] else ''
    following=expanded[positions[last]+1] if positions[last]+1<len(expanded) else ''
    def joined(left,right):
     if not left or not right or left.isspace() or right.isspace():return False
     if left.isdigit() and (right.isdigit() or right in '.,%') or right.isdigit() and (left.isdigit() or left in '.,+−-'):return True
     return left.isalnum() and right.isalnum() and not(cjk(left) and cjk(right))
    if not joined(prev,line[0]) and not joined(line[-1],following):approved[n]=True
  start=end
 return approved
