"""Reconcile OCR text regions only against independently agreeing visible text."""
from collections import Counter
from contextlib import closing
import math
import unicodedata


def characters(text):
    return Counter(c for c in unicodedata.normalize('NFKC', text)
                   if not c.isspace() and unicodedata.category(c) != 'Cc')


def reconcile(page, native, blocks):
    from pdfplumber.utils import extract_words
    from layout import words_to_blocks
    width, height = page.get_size()
    if tuple(page.get_bbox()) != (0, 0, width, height):
        return 0
    chars = native.dedupe_chars(tolerance=.5).chars
    controls = [i for i,c in enumerate(chars) if any(unicodedata.category(v)=='Cc' and not v.isspace() for v in c['text'])]
    blank_controls = set()
    if controls:
        with closing(page.render(scale=2)) as bitmap:
            image = bitmap.to_pil().convert('RGB')
            for index in controls:
                c=chars[index]
                bounds=(math.floor(c['x0']*2),math.floor(c['top']*2),math.ceil(c['x1']*2),math.ceil(c['bottom']*2))
                if bounds[0]<0 or bounds[1]<0 or bounds[2]>image.width or bounds[3]>image.height or bounds[2]<=bounds[0] or bounds[3]<=bounds[1]:
                    continue
                # Include adjacent background: a solid ink rectangle filling a
                # glyph box is not proof of a blank character.
                sample = (bounds[0], bounds[1], min(image.width, bounds[2]+2), bounds[3])
                if all(high-low<=1 for low,high in image.crop(sample).getextrema()):
                    blank_controls.add(index)
    proposals = []
    with closing(page.get_textpage()) as independent:
        for block in blocks:
            if block['kind'] not in {'paragraph','heading','list'}:
                continue
            for padding in (0, 2, 4, 6):
                x0,y0,x1,y1=block['bbox']
                bounds=(max(0,x0-padding),max(0,y0-padding),min(width,x1+padding),min(height,y1+padding))
                x0,y0,x1,y1=bounds
                area=(x1-x0)*(y1-y0)
                if any(max(0,min(x1,im['x1'])-max(x0,im['x0'])) * max(0,min(y1,im['bottom'])-max(y0,im['top'])) > area*.15 for im in native.images):
                    break
                selected={i for i,c in enumerate(chars) if x0<=c['x0']<=c['x1']<=x1 and y0<=c['top']<=c['bottom']<=y1}
                if (selected & set(controls)) - blank_controls:
                    continue
                source=''.join(chars[i]['text'] for i in sorted(selected))
                # Geometry-sorted runs do not establish bidirectional logical
                # order. Leave these regions to OCR rather than swapping words.
                if any(unicodedata.bidirectional(c) in {'R', 'AL', 'AN'} for c in source):
                    continue
                expected=characters(source)
                if sum(expected.values()) < max(4,sum(characters(block.get('text','')).values())*.6):
                    continue
                other=independent.get_text_bounded(x0,height-y1,x1,height-y0)
                if expected != characters(other):
                    continue
                clean=[chars[i] for i in sorted(selected) if all(unicodedata.category(c)!='Cc' for c in chars[i]['text'])]
                paragraphs=words_to_blocks(extract_words(clean,return_chars=True,x_tolerance=2,y_tolerance=1),width,height)
                value='\n'.join(p['text'] for p in paragraphs)
                if characters(value) != expected:
                    continue
                proposals.append((block,selected,paragraphs,value,bounds))
                break
    count=0
    for block,selected,paragraphs,value,bounds in proposals:
        # No character may be assigned to two OCR regions, even when padding
        # around small annotations was needed. Ambiguous regions remain OCR.
        if any(selected & other for target,other,*_ in proposals if target is not block):
            continue
        runs=[]
        for index,paragraph in enumerate(paragraphs):
            for j,run in enumerate(paragraph['runs']):
                runs.append({**run,'text':('\n' if index and not j else '')+run['text']})
        block.update(text=value,runs=runs,source='native',bbox=list(bounds),native_text_reconciled=True)
        count+=1
    return count
