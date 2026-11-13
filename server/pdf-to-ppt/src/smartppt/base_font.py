"""Reproduce only PDFium's pinned, BSD-licensed standard Helvetica glyphs.

No uploaded font is saved or embedded. A source must be unembedded Helvetica,
match the reviewed built-in CFF byte-for-byte, and use supported Unicode glyphs.
The generated full TrueType face is used both for rendering and PPT embedding.
"""
import ctypes
import unicodedata
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import pypdfium2 as pdfium
from .config import ConversionError

FAMILY='SmartPDF Base Sans'
SOURCE_SHA256='a02339e95d20db14cbdfc1c6baf359cd36a091d5434925c3a4040f60e1a1af9e'
SOURCE_BYTES=15025


def font_data(font):
    length=ctypes.c_ulong()
    raw=pdfium.raw
    if not raw.FPDFFont_GetFontData(font,None,0,ctypes.byref(length)) or length.value!=SOURCE_BYTES:
        return None
    buffer=(ctypes.c_ubyte*length.value)()
    if not raw.FPDFFont_GetFontData(font,buffer,length.value,ctypes.byref(length)) or length.value!=SOURCE_BYTES:
        return None
    data=bytes(buffer)
    return data if sha256(data).hexdigest()==SOURCE_SHA256 else None


@lru_cache(maxsize=1)
def builtin_data():
    with pdfium.PdfDocument.new() as document:
        font=pdfium.raw.FPDFText_LoadStandardFont(document,b'Helvetica')
        if not font:raise ConversionError('portable_base_font_unavailable')
        try:data=font_data(font)
        finally:pdfium.raw.FPDFFont_Close(font)
    if data is None:raise ConversionError('portable_base_font_integrity_failed')
    return data


@lru_cache(maxsize=1)
def approved_cmap():
    from fontTools.cffLib import CFFFontSet
    from fontTools.agl import toUnicode
    fonts=CFFFontSet();fonts.decompile(BytesIO(builtin_data()),None)
    return {ord(text):name for name in fonts[fonts.fontNames[0]].charset
            for text in [toUnicode(name)] if len(text)==1}


def source_family(font,text,*,bold=False,italic=False):
    if (bold or italic or font.get_base_name()!='Helvetica' or pdfium.raw.FPDFFont_GetIsEmbedded(font)!=0
            or font_data(font) is None):return None
    try:
        cmap=approved_cmap()
        if all(ord(c) in cmap or c in '\t\r\n' for c in text+unicodedata.normalize('NFKC',text)):return FAMILY
    except ConversionError:
        pass  # An optional font must never change input eligibility.
    return None


@lru_cache(maxsize=1)
def ttf_bytes():
    from fontTools.cffLib import CFFFontSet
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.boundsPen import BoundsPen
    fonts=CFFFontSet();fonts.decompile(BytesIO(builtin_data()),None);face=fonts[fonts.fontNames[0]]
    # The reviewed CFF uses 1000 units/em; vertical metrics cover its glyph bounds.
    if list(face.FontMatrix)!=[.001,0,0,.001,0,0]:
        raise ConversionError('portable_base_font_matrix_mismatch')
    ascent,descent=round(face.FontBBox[3]),round(face.FontBBox[1])
    glyphs={};metrics={}
    for name in face.charset:
        charstring=face.CharStrings[name];pen=TTGlyphPen(None)
        charstring.draw(Cu2QuPen(pen,max_err=.1,reverse_direction=True));glyphs[name]=pen.glyph()
        bounds=BoundsPen(None);charstring.draw(bounds)
        metrics[name]=(round(charstring.width),round(bounds.bounds[0]) if bounds.bounds else 0)
    builder=FontBuilder(1000,isTTF=True);builder.setupGlyphOrder(face.charset)
    builder.setupCharacterMap(approved_cmap());builder.setupGlyf(glyphs);builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ascent,descent=descent)
    license_text=Path(__file__).with_name('BSD-PDFium-base-font.txt').read_text()
    builder.setupNameTable({'familyName':FAMILY,'styleName':'Regular','uniqueFontIdentifier':'SmartPDFBaseSans-Regular-v1',
        'fullName':FAMILY+' Regular','psName':'SmartPDFBaseSans-Regular','version':'Version 1.0',
        'copyright':'Copyright 2014 PDFium Authors. Original code copyright 2014 Foxit Software Inc.',
        'licenseDescription':license_text})
    builder.setupOS2(sTypoAscender=ascent,sTypoDescender=descent,usWinAscent=ascent,usWinDescent=-descent,fsType=0)
    builder.setupPost();builder.setupMaxp()
    builder.font['head'].created=builder.font['head'].modified=2082844800
    builder.font.recalcTimestamp=False
    result=BytesIO();builder.font.save(result);return result.getvalue()
