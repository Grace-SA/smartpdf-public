"""Independent geometry-first word diagnostic for equal-size source/rendered PDFs.

Strict words require mutual-nearest geometry pairing, exact NFKC text and a 2pt
edge tolerance. Poppler boxes differ from ink boxes; tokenization splits and
non-matches require inspection. This tool does not certify correctness.
"""
from pathlib import Path
import subprocess,json,math,unicodedata
from xml.etree import ElementTree as E

def words(path):
    xml=subprocess.check_output(['pdftotext','-bbox-layout','-enc','UTF-8',str(path),'-'],timeout=60)
    doc=E.fromstring(xml);pages=[]
    for p in doc.iter():
      if p.tag.endswith('}page'):
        out=[]
        dimensions=(float(p.get('width')),float(p.get('height')))
        for n in p.iter():
          if n.tag.endswith('}word'):
            out.append({'text':''.join(n.itertext()),'bbox':[float(n.get(k)) for k in ['xMin','yMin','xMax','yMax']]})
        pages.append((dimensions,out))
    return pages

def compare(source,rendered):
    result=[]
    references,predictions=words(source),words(rendered)
    if len(references)!=len(predictions):raise ValueError('page count mismatch')
    for (rd,ref),(pd,pred) in zip(references,predictions):
      if max(abs(a-b) for a,b in zip(rd,pd))>.01:raise ValueError('page dimensions differ; coordinate transform required')
      # Geometry first: a rendered word chooses its closest reference center,
      # regardless of text. Require a unique bidirectional match within 2pt edges.
      def center(w):l,t,r,b=w['bbox'];return ((l+r)/2,(t+b)/2)
      def nearest(w,rows):
        if not rows:return None
        c=center(w);ds=[math.dist(c,center(r)) for r in rows];m=min(ds)
        return ds.index(m) if ds.count(m)==1 else None
      mapping=[nearest(p,ref) for p in pred];back=[nearest(r,pred) for r in ref]
      rows=[]
      for i,r in enumerate(ref):
        j=back[i];p=pred[j] if j is not None and mapping[j]==i else None
        edge=max(abs(a-b) for a,b in zip(r['bbox'],p['bbox'])) if p else None
        exact=p is not None and unicodedata.normalize('NFKC',r['text'])==unicodedata.normalize('NFKC',p['text'])
        rows.append({'source':r,'rendered':p,'edge_error_points':edge,'exact_text':exact,'strict_pass':exact and edge<=2})
      unpaired=[p for j,p in enumerate(pred) if mapping[j] is None or back[mapping[j]]!=j]
      result.append({'unpaired_rendered_words':len(unpaired),'unpaired_rendered':unpaired,'source_words':len(ref),'rendered_words':len(pred),'exact_words':sum(r['exact_text'] for r in rows),'strict_words':sum(r['strict_pass'] for r in rows),'failures':[r for r in rows if not r['strict_pass']]})
    return result
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--source',type=Path,required=True)
 parser.add_argument('--rendered',type=Path,required=True)
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args()
 result=compare(args.source,args.rendered)
 # Never overwrite an existing evidence artifact or an input file.
 with args.output.open('x') as f:json.dump({'diagnostic_only':True,'reference':'Poppler bbox-layout, not human truth','pages':result},f,indent=2)
