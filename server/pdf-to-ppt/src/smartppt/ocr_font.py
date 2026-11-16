"""Choose a measured Latin fallback family/style from installed font candidates.

OCR does not recover original font identities. Compare glyph shapes at the
observed ink bounds; this only estimates a fallback and does not embed fonts.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CANDIDATES = [(family,family+suffix+'.ttf',bold,italic)
              for family in ('Arial','Times New Roman','Courier New')
              for suffix,bold,italic in [('',False,False),(' Bold',True,False),
                                        (' Italic',False,True),(' Bold Italic',True,True)]]


def latin_font(text, crop, background, directory):
    if not text or len(text)>512:return None
    if any(ord(c)>0x024f for c in text):
        from .cjk_font import cjk_font
        return cjk_font(text,crop,background)
    pixels=np.asarray(crop,dtype=float)
    ink=np.max(np.abs(pixels-np.array(background)),axis=2)
    if ink.max()<1:return None
    ink/=ink.max();best=None;baseline=None
    for family,filename,bold,italic in CANDIDATES:
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
        candidate={'family':family,'bold':bold,'italic':italic,'path':str(path),'error':error,'matched':True}
        if family=='Arial' and not bold and not italic:baseline=candidate
        if best is None or error<best['error']:best=candidate
    if best and baseline:
        margin=.12 if best['family']=='Courier New' else .06
        if best['error']>.20 or (best!=baseline and baseline['error']-best['error']<margin):
            from .font_words import rank_words
            ranked=rank_words(text,crop,background,directory,CANDIDATES)
            default=next((r for r in ranked if r['family']=='Arial' and not r['bold'] and not r['italic']),None)
            from .cjk_font import cjk_font
            open_choice=cjk_font(text,crop,background,require_cjk=False)
            word_choice=None
            if ranked and default and ranked[0]['error']<=.30 and default['error']-ranked[0]['error']>=.025:
                word_choice=dict(ranked[0],matched=ranked[0]['error']<=.20,comparison='individual word ink; interword spacing excluded')
            competitor=word_choice or baseline
            if open_choice and open_choice['error']<=.20 and competitor['error']-open_choice['error']>=.06:
                return open_choice
            if word_choice:return word_choice
            return dict(baseline,matched=False)
    if best is None:
        from .cjk_font import cjk_font
        return cjk_font(text,crop,background,require_cjk=False)
    return best
