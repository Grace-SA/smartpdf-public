"""Estimate available open CJK family and weight from measured source ink."""
import os
from pathlib import Path
from functools import lru_cache
import numpy as np
from PIL import Image,ImageDraw,ImageFont

@lru_cache(maxsize=12)
def face(path,stamp,weight):
 font=ImageFont.truetype(path,80)
 axes=font.get_variation_axes()
 font.set_variation_by_axes([weight]+[a['default'] for a in axes[1:]])
 return font

def cjk_font(text,crop,background,require_cjk=True):
 if require_cjk and not any(0x3400<=ord(c)<=0x9fff or 0x20000<=ord(c)<=0x323af for c in text):return None
 pixels=np.asarray(crop,dtype=float);ink=np.max(np.abs(pixels-np.asarray(background)),axis=2)
 if ink.max()<1:return None
 ink/=ink.max();choices=[]
 for family,key in [('Noto Sans SC','SMARTPPT_CJK_FONT'),('Noto Serif SC','SMARTPPT_CJK_SERIF_FONT')]:
  value=os.getenv(key)
  if not value:continue
  path=Path(value)
  if not path.is_file():continue
  for weight in [100 if family=='Noto Sans SC' else 200,400,700]:
   try:font=face(str(path),path.stat().st_mtime_ns,weight)
   except (OSError,ValueError):continue
   l,t,r,b=font.getbbox(text)
   if not 0<r-l<=16384 or not 0<b-t<=512:continue
   mask=Image.new('L',(r-l,b-t));ImageDraw.Draw(mask).text((-l,-t),text,font=font,fill=255);bounds=mask.getbbox()
   if not bounds:continue
   mask=mask.crop(bounds).resize(crop.size,Image.Resampling.LANCZOS)
   error=float(np.abs(ink-np.asarray(mask,dtype=float)/255).mean())
   choices.append({'family':'SmartPDF Sans100' if weight==100 else 'SmartPDF Serif200' if weight==200 else family,'weight':weight,'bold':weight==700,'italic':False,'path':str(path),'error':error,'matched':error<=.20,'comparison':'open CJK family and weight ink'})
 if not choices:return None
 choices.sort(key=lambda r:r['error']);return choices[0]
