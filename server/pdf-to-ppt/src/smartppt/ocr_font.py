"""Choose a measured Latin fallback family/style from installed font candidates.

OCR does not recover original font identities. Compare glyph shapes at the
observed ink bounds; this only estimates a fallback and does not embed fonts.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CANDIDATES = [('Arial','Arial.ttf',False),('Arial','Arial Bold.ttf',True),
              ('Times New Roman','Times New Roman.ttf',False),
              ('Times New Roman','Times New Roman Bold.ttf',True),
              ('Courier New','Courier New.ttf',False),('Courier New','Courier New Bold.ttf',True)]


def latin_font(text, crop, background, directory):
    if not text or len(text)>512 or any(ord(c)>0x024f for c in text):
        return None
    pixels=np.asarray(crop,dtype=float)
    ink=np.max(np.abs(pixels-np.array(background)),axis=2)
    if ink.max()<1:return None
    ink/=ink.max();best=None;baseline=None
    for family,filename,bold in CANDIDATES:
        path=Path(directory)/filename
        if not path.is_file():continue
        font=ImageFont.truetype(str(path),80)
        l,t,r,b=font.getbbox(text)
        if not 0<r-l<=8192 or not 0<b-t<=512:continue
        mask=Image.new('L',(r-l,b-t));ImageDraw.Draw(mask).text((-l,-t),text,font=font,fill=255)
        bounds=mask.getbbox()
        if not bounds:continue
        mask=mask.crop(bounds).resize(crop.size,Image.Resampling.LANCZOS)
        error=float(np.abs(ink-np.asarray(mask,dtype=float)/255).mean())
        candidate={'family':family,'bold':bold,'path':str(path),'error':error,'matched':True}
        if family=='Arial' and not bold:baseline=candidate
        if best is None or error<best['error']:best=candidate
    if best and baseline:
        margin=.12 if best['family']=='Courier New' else .06
        if best['error']>.20 or (best!=baseline and baseline['error']-best['error']<margin):
            return dict(baseline,matched=False)
    return best
