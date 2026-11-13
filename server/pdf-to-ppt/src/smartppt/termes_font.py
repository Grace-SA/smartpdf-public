"""Optional pinned TeX Gyre Termes derivative for explicit Nimbus Roman faces.

Only reviewed full upstream fonts are read, never a font from an uploaded PDF.
Renamed TrueType output is shared by local rendering and the embedded payload.
"""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
from .config import ConversionError

FAMILY='SmartPDF Termes'
FACES={
 'regular':('texgyretermes-regular.otf',140932,'cc3fe7c707b81428d23d54df3eadd9228a2bf6a4d43125d94df56f5f63134659'),
 'bold':('texgyretermes-bold.otf',139480,'2fb3e952065fa153c7e4e64e04b98b9d79225739b6025aa3f0f0782d299ff61e'),
 'italic':('texgyretermes-italic.otf',141324,'6dd103a1672e50568cd2f8a706ccd48443d44d7d073a59d2286f4e6f746575d6'),
 'boldItalic':('texgyretermes-bolditalic.otf',144180,'1bf6af99cb0e26c12951317032d79b96ae009551e59ccf02a5b24f325ecfec87'),
}


def face_name(name):
 name=re.sub(r'^[A-Z]{6}\+','',name).lower().replace(' ','')
 match=re.fullmatch(r'nimbusromno9l-(regu|medi|reguital|mediital)',name)
 if match:return {'regu':'regular','medi':'bold','reguital':'italic','mediital':'boldItalic'}[match[1]]
 match=re.fullmatch(r'(?:nimbusroman|texgyretermes)-(regular|bold|italic|bolditalic)',name)
 if match:return 'boldItalic' if match[1]=='bolditalic' else match[1]
 return None


def approved_data(style):
 if style not in FACES:raise ConversionError('portable_termes_style_unsupported')
 root=os.getenv('SMARTPPT_TERMES_FONT_DIR')
 if not root:raise ConversionError('portable_termes_font_missing')
 name,size,digest=FACES[style];path=Path(root)/name
 try:
  if path.stat().st_size!=size:raise ConversionError('portable_termes_font_integrity_failed')
  data=path.read_bytes()
 except OSError as error:raise ConversionError('portable_termes_font_missing') from error
 if len(data)!=size or sha256(data).hexdigest()!=digest:raise ConversionError('portable_termes_font_integrity_failed')
 return data


def source_family(name):
 style=face_name(name)
 if style is None or not os.getenv('SMARTPPT_TERMES_FONT_DIR'):return None
 root=Path(os.environ['SMARTPPT_TERMES_FONT_DIR'])
 # Rendering can encounter synthetic bold/italic runs; configure the entire
 # reviewed family or retain the existing source-font policy.
 if not all((root/filename).is_file() for filename,_,_ in FACES.values()):return None
 try:approved_data(style)
 except ConversionError:return None
 return FAMILY


def ttf_bytes(style):
 # Verify each read before using a cached conversion. Replacing an operator
 # file after an earlier job must not bypass integrity checking.
 return convert_font(approved_data(style),style)


@lru_cache(maxsize=4)
def convert_font(data,style):
 from fontTools.ttLib import TTFont
 from fontTools.fontBuilder import FontBuilder
 from fontTools.pens.ttGlyphPen import TTGlyphPen
 from fontTools.pens.cu2quPen import Cu2QuPen
 if style not in FACES or sha256(data).hexdigest()!=FACES[style][2]:
  raise ConversionError('portable_termes_font_integrity_failed')
 with TTFont(BytesIO(data)) as font:
  if font['OS/2'].fsType!=12 or font['head'].unitsPerEm!=1000 or 'CFF ' not in font:
   raise ConversionError('portable_termes_font_integrity_failed')
  glyphset=font.getGlyphSet();glyphs={}
  for name in font.getGlyphOrder():
   pen=TTGlyphPen(None);glyphset[name].draw(Cu2QuPen(pen,max_err=.1,reverse_direction=True));glyphs[name]=pen.glyph()
  del font['CFF '];font.sfntVersion='\x00\x01\x00\x00'
  builder=FontBuilder(font=font,isTTF=True);builder.isTTF=True
  post={name:getattr(font['post'],name) for name in ('italicAngle','underlinePosition','underlineThickness','isFixedPitch','minMemType42','maxMemType42','minMemType1','maxMemType1')}
  builder.setupGlyf(glyphs);builder.setupMaxp();builder.setupPost(**post)
  title={'regular':'Regular','bold':'Bold','italic':'Italic','boldItalic':'Bold Italic'}[style]
  names={1:FAMILY,2:title,3:'SmartPDFTermes-'+style+'-v1',4:FAMILY+' '+title,5:'Version 1.0; derived from TeX Gyre Termes 2.004',6:'SmartPDFTermes-'+style,16:FAMILY,17:title}
  for ident,value in names.items():
   for platform,encoding,language in ((3,1,0x409),(1,0,0)):font['name'].setName(value,ident,platform,encoding,language)
  # Preserve upstream copyright and layout/cmap tables. Include the full
  # licenses and modification manifest in the delivered font, not just URLs.
  folder=Path(__file__).parent
  notice='\n\n'.join((folder/name).read_text() for name in ('GFL-Termes.txt','LPPL-1.3c.txt','MANIFEST-SmartPDFTermes.txt'))
  font['name'].names=[n for n in font['name'].names if n.nameID not in (13,14)]
  font['name'].setName(notice,13,3,1,0x409)
  font['name'].setName('https://tug.org/fonts/licenses/GUST-FONT-LICENSE.txt',14,3,1,0x409)
  font['head'].fontRevision=1.0
  font['head'].created=font['head'].modified=2082844800;font.recalcTimestamp=False
  result=BytesIO();font.save(result);return result.getvalue()
