"""Independent truth evaluation; image fallbacks never count as editable text.

Region assignment uses geometry rather than recognized text. Metrics normalize
NFKC and whitespace only, preserving case, punctuation and every digit.
"""
from collections import Counter,defaultdict
import math
import re
from .quality import normalized


def edit_counts(expected,actual):
    """Exact Levenshtein S/D/I counts with deterministic ties and linear memory."""
    a,b=normalized(expected),normalized(actual)
    if a==b:return {'reference_characters':len(a),'predicted_characters':len(b),'substitutions':0,'deletions':0,'insertions':0,'correct_characters':len(a)}
    if len(a)*len(b)>25_000_000:raise ValueError('evaluation region too large; use smaller independently positioned regions')
    previous=[(j,0,0,j) for j in range(len(b)+1)]
    for i,ca in enumerate(a,1):
        current=[(i,0,i,0)]
        for j,cb in enumerate(b,1):
            cost,s,d,ins=previous[j-1];diagonal=(cost+(ca!=cb),s+(ca!=cb),d,ins)
            cost,s,d,ins=previous[j];deletion=(cost+1,s,d+1,ins)
            cost,s,d,ins=current[-1];insertion=(cost+1,s,d,ins+1)
            current.append(min((diagonal,deletion,insertion),key=lambda x:x[0]))
        previous=current
    _,s,d,ins=previous[-1]
    return {'reference_characters':len(a),'predicted_characters':len(b),
            'substitutions':s,'deletions':d,'insertions':ins,'correct_characters':len(a)-s-d}


COUNT_KEYS=('reference_characters','predicted_characters','correct_characters','substitutions','deletions','insertions')


def rates(counts):
    n=counts['reference_characters'];p=counts['predicted_characters'];correct=counts['correct_characters']
    errors=sum(counts[k] for k in ('substitutions','deletions','insertions'));cer=errors/n if n else None
    return {**counts,'character_error_rate':cer,'character_accuracy':max(0,1-cer) if cer is not None else None,
            'character_recall':correct/n if n else None,'character_precision':correct/p if p else None}


def numbers(text):
    return re.findall(r'[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?',normalized(text).replace('\u2212','-'))


def validate_box(box):
    if (len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in box)
        or box[2]<=box[0] or box[3]<=box[1]):raise ValueError('invalid evaluation bounds')


def assign_regions(truth,predictions):
    """Assign each run once; overlapping/ambiguous regions remain unmatched."""
    grouped=defaultdict(list);unmatched=[]
    for row in truth:validate_box(row['bbox'])
    for prediction in predictions:
        validate_box(prediction['bbox']);l,t,r,b=prediction['bbox'];cx,cy=(l+r)/2,(t+b)/2
        candidates=[i for i,row in enumerate(truth) if row['bbox'][0]<=cx<=row['bbox'][2] and row['bbox'][1]<=cy<=row['bbox'][3]]
        if len(candidates)==1:grouped[candidates[0]].append(prediction)
        else:unmatched.append(prediction)
    return grouped,unmatched


def evaluate_page(truth,predictions,*,truth_verified=False,position_tolerance=2.0):
    if not truth_verified:return {'measured':False,'reason':'independent_ground_truth_missing','editable_success':None}
    if not math.isfinite(position_tolerance) or position_tolerance<0:raise ValueError('invalid position tolerance')
    if len({r['id'] for r in truth})!=len(truth):raise ValueError('duplicate truth region identifiers')
    ordered=any('reading_order' in p for p in predictions)
    if ordered and (any(type(p.get('reading_order')) is not int for p in predictions)
                    or len({p['reading_order'] for p in predictions})!=len(predictions)):
        raise ValueError('invalid prediction reading order')
    grouped,unmatched=assign_regions(truth,predictions);total=Counter();regions=[]
    for index,row in enumerate(truth):
        parts=sorted(grouped[index],key=lambda p:p['reading_order'] if ordered else (p['bbox'][1],p['bbox'][0]))
        # Do not insert synthetic separators between characters: a combining
        # accent may belong to the preceding glyph before NFKC normalization.
        text=''.join(p['text'] for p in parts);counts=edit_counts(row['text'],text);total.update(counts)
        expected_numbers=numbers(row['text']);actual_numbers=numbers(text);position_error=None
        if parts:
            combined=[min(p['bbox'][0] for p in parts),min(p['bbox'][1] for p in parts),max(p['bbox'][2] for p in parts),max(p['bbox'][3] for p in parts)]
            position_error=max(abs(a-b) for a,b in zip(row['bbox'],combined))
        regions.append({'id':row['id'],**rates(counts),'exact_text':normalized(row['text'])==normalized(text),
            'numeric_exact':expected_numbers==actual_numbers,'has_numbers':bool(expected_numbers),
            'position_error':position_error,'position_pass':position_error is not None and position_error<=position_tolerance})
    extra=sum(len(normalized(p['text'])) for p in unmatched);total.update(predicted_characters=extra,insertions=extra)
    for key in COUNT_KEYS:total.setdefault(key,0)
    summary=rates(dict(total));numeric_regions=[r for r in regions if r['has_numbers']]
    geometry_pass=sum(r['position_pass'] for r in regions);numeric_pass=sum(r['numeric_exact'] for r in numeric_regions)
    success=(bool(summary['reference_characters']) and summary['character_error_rate']<=.001
             and summary['character_recall']>=.99 and numeric_pass==len(numeric_regions)
             and geometry_pass==len(regions) and extra==0)
    if not truth and not predictions:success=True
    return {'measured':True,**summary,'normalization':'NFKC; whitespace removed; punctuation/case retained',
            'regions':regions,'unmatched_prediction_characters':extra,'numeric_regions':len(numeric_regions),
            'numeric_regions_exact':numeric_pass,'position_regions':len(regions),'position_regions_passed':geometry_pass,'editable_success':success}


def wilson(successes,total,z=1.959963984540054):
    if not total:return None
    p=successes/total;denominator=1+z*z/total;center=(p+z*z/(2*total))/denominator
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return [max(0,center-half),min(1,center+half)]


def summarize_documents(documents):
    """Unknown accuracy never becomes 100%; retain every eligible denominator."""
    accepted=[d for d in documents if d['eligible']];generated=[d for d in accepted if d['generated']]
    measured=[d for d in accepted if d.get('pages') and all(p.get('measured') for p in d['pages'])]
    assessed=[d for d in measured if type(d.get('structure_verified')) is bool and type(d.get('render_verified')) is bool]
    successful=[d for d in measured if d['generated'] and all(p['editable_success'] for p in d['pages'])
                and d.get('structure_verified') is True and d.get('render_verified') is True]
    counts=Counter()
    for d in measured:
        for page in d['pages']:counts.update({k:page[k] for k in COUNT_KEYS})
    for key in COUNT_KEYS:counts.setdefault(key,0)
    return {'input_documents':len(documents),'eligible_documents':len(accepted),'preflight_excluded_documents':len(documents)-len(accepted),
        'generated_documents':len(generated),'file_generation_rate':len(generated)/len(accepted) if accepted else None,
        'truth_measured_documents':len(measured),'truth_missing_documents':len(accepted)-len(measured),
        'fully_assessed_documents':len(assessed),'verified_editable_success_documents':len(successful),
        'verified_editable_success_rate':len(successful)/len(accepted) if accepted and len(assessed)==len(accepted) else None,
        'verified_success_lower_bound':len(successful)/len(accepted) if accepted else None,
        'success_rate_is_complete':len(assessed)==len(accepted),'success_wilson_95':wilson(len(successful),len(accepted)) if len(assessed)==len(accepted) else None,
        'text':rates(dict(counts))}


def main():
    """Evaluate an explicit, local-only truth/prediction manifest."""
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();manifest=json.loads(args.input.read_text());documents=[]
    for document in manifest['documents']:
        pages=[evaluate_page(p.get('truth',[]),p.get('predictions',[]),truth_verified=p.get('truth_verified') is True,
                             position_tolerance=manifest.get('position_tolerance_points',2)) for p in document.get('pages',[])]
        documents.append({**{k:v for k,v in document.items() if k!='pages'},'pages':pages})
    args.output.write_text(json.dumps({'documents':documents,'summary':summarize_documents(documents)},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
