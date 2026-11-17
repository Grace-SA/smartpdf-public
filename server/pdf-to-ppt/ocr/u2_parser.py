"""Strict single-image parser for the documented Unlimited OCR 2 block format."""
import re

PATTERN=re.compile(r'<BLOCK>\s*([a-z_]+)(?:<LEVEL(\d+)>)?\s*\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\](?:<LEVEL(\d+)>)?\s*<FORK>',re.I)

def parse_blocks(text):
    pages=text.split('<PAGE>')
    if pages and not pages[0].strip():pages=pages[1:]
    blocks=[]
    for number,page in enumerate(pages,1):
        matches=list(PATTERN.finditer(page))
        if page.strip() and not matches:raise ValueError('unsupported OCR block format')
        for i,match in enumerate(matches):
            box=[int(match.group(j)) for j in range(3,7)]
            if not all(0<=v<=1000 for v in box) or box[0]>=box[2] or box[1]>=box[3]:raise ValueError('invalid OCR block coordinates')
            content=page[match.end():matches[i+1].start() if i+1<len(matches) else len(page)].strip()
            blocks.append({'label':match.group(1).lower(),'bbox':box,'level':int(match.group(2) or match.group(7)) if match.group(2) or match.group(7) else None,
                'content':content,'page':number})
    return blocks
