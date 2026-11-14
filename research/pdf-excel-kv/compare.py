"""Exact execution-trace multiset plus independent worksheet/cell comparison."""
import argparse,copy,hashlib,json
from collections import Counter
from pathlib import Path
import openpyxl
p=argparse.ArgumentParser();p.add_argument('--baseline',action='append',required=True,type=Path);p.add_argument('--candidate',required=True,type=Path);p.add_argument('--report',required=True,type=Path);args=p.parse_args()
def read(root,name):return json.loads((root/name).read_text())
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def trace(t):return canonical([t['logits'],t['prediction']])
refs=[read(root,'result.json')for root in args.baseline];candidate=read(args.candidate,'result.json')
a=[t for root in args.baseline for t in read(root,'traces.json')];b=read(args.candidate,'traces.json')
# Calls may complete in a different order; preserve counts, not just a set.
trace_equal=Counter(map(trace,a))==Counter(map(trace,b))
assert trace_equal,'Execution traces differ'
report=dict(traceCount=len(b),tokenSteps=sum(len(t['logits'])for t in b),traceMultisetExact=trace_equal,status=candidate['status'],semanticDifferences=[],geometryDifferences=[])
assert all(r['status']==candidate['status']for r in refs),'Outcome changed'
if candidate['status']=='refused':
 assert len(refs)==1 and refs[0]['result']==candidate['result'],'Refusal changed'
 assert not(args.candidate/'output.xlsx').exists()and not(args.baseline[0]/'output.xlsx').exists(),'Refusal wrote a workbook'
else:
 books=[openpyxl.load_workbook(root/'output.xlsx')for root in args.baseline];new=openpyxl.load_workbook(args.candidate/'output.xlsx');names=[name for w in books for name in w.sheetnames]
 assert len(names)==len(set(names)) and set(names)==set(new.sheetnames),'Sheet set changed'
 assert names==new.sheetnames,'Sheet order changed'
 def semantic(c):return(c.value,c.data_type,c.number_format,c.comment.text if c.comment else None,*(str(copy.copy(getattr(c,k)))for k in ('font','fill','border','alignment','protection')))
 for sheet in new:
  old=next(w[sheet.title]for w in books if sheet.title in w.sheetnames)
  assert(old.max_row,old.max_column)==(sheet.max_row,sheet.max_column),(sheet.title,'shape')
  assert sorted(map(str,old.merged_cells))==sorted(map(str,sheet.merged_cells)),(sheet.title,'merges')
  for row in old:
   for c in row:
    if semantic(c)!=semantic(sheet[c.coordinate]):report['semanticDifferences'].append([sheet.title,c.coordinate])
  for name,size in [('row_dimensions','height'),('column_dimensions','width')]:
   aa,bb=getattr(old,name),getattr(sheet,name);assert set(aa)==set(bb),(sheet.title,name,'dimension keys')
   for k in aa:
    x,y=getattr(aa[k],size),getattr(bb[k],size)
    if x!=y:report['geometryDifferences'].append(dict(sheet=sheet.title,kind=size,key=k,before=x,after=y))
 assert not report['semanticDifferences'],'Cell semantic changes'
 for w in books+[new]:w.close()
args.report.write_text(json.dumps(report,indent=2));print(json.dumps(report))
