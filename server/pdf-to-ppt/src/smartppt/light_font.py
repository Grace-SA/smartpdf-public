"""Optional, full licensed CMU Light derivative; never read uploaded fonts.

A separate regular-only family avoids family/style selection ambiguities. The
pinned upstream glyph, shaping and metric tables are retained without subsetting.
"""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import os
import stat
from pathlib import Path
import unicodedata
from .config import ConversionError

FAMILY='SmartPDF CMU Typewriter Light'
FILENAME='cmunbtl.ttf'
SIZE=410116
SHA256='093ceab998d9bb0f4f1312fd10980b3919e557ad594080f7da8c8938a38e4a49'
NOTICE=('SmartPDF derivative version 1.0, based on CMU 0.7.0 cmunbtl.ttf. '
        'Renamed as a separate regular-only SmartPDF CMU Typewriter Light family; '
        'updated naming, version and license notices. Original glyphs, Unicode '
        'mapping, shaping, advances, metrics and embedding permissions retained. '
        'No endorsement by upstream authors is implied. Distributed under SIL OFL 1.1.')


def approved_data():
    root=os.getenv('SMARTPPT_CMU_FONT_DIR')
    if not root:raise ConversionError('portable_light_font_missing')
    path=Path(root)/FILENAME
    try:
        # Read at most one byte beyond the exact pinned size, including if the
        # operator replaces a file between stat and read.
        descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NONBLOCK',0))
        with os.fdopen(descriptor,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size!=SIZE:
                raise ConversionError('portable_light_font_integrity_failed')
            data=stream.read(SIZE+1)
    except OSError as error:raise ConversionError('portable_light_font_missing') from error
    if len(data)!=SIZE or sha256(data).hexdigest()!=SHA256:
        raise ConversionError('portable_light_font_integrity_failed')
    return data


@lru_cache(maxsize=1)
def convert_font(data):
    if len(data)!=SIZE or sha256(data).hexdigest()!=SHA256:
        raise ConversionError('portable_light_font_integrity_failed')
    from fontTools.ttLib import TTFont
    with TTFont(BytesIO(data),recalcBBoxes=False,recalcTimestamp=False) as font:
        if font['OS/2'].fsType!=0 or font['OS/2'].usWeightClass!=200 or font['post'].isFixedPitch!=0:
            raise ConversionError('portable_light_font_integrity_failed')
        # Remove every language/platform spelling of old identity fields. Keep
        # upstream copyright/author metadata, and supply typographic/WWS names
        # so consumers cannot regroup this face with the original family.
        names={1:FAMILY,2:'Regular',3:'SmartPDFCMUTypewriterLight-Regular-v1',
               4:FAMILY+' Regular',5:'Version 1.0; derived from CMU 0.7.0',
               6:'SmartPDFCMUTypewriterLight-Regular',16:FAMILY,17:'Regular',
               18:FAMILY+' Regular',20:'SmartPDFCMUTypewriterLight-Regular',
               21:FAMILY,22:'Regular',25:'SmartPDFCMUTypewriterLight'}
        replaced=set(names)|{13,14}
        font['name'].names=[n for n in font['name'].names if n.nameID not in replaced]
        for ident,value in names.items():
            for platform,encoding,language in ((3,1,0x409),(1,0,0)):
                font['name'].setName(value,ident,platform,encoding,language)
        license_text=Path(__file__).with_name('OFL-CMU.txt').read_text()
        font['name'].setName(license_text+'\n\n'+NOTICE,13,3,1,0x409)
        font['name'].setName('https://openfontlicense.org/',14,3,1,0x409)
        # FontTools may otherwise recompute OS/2 first/last character indices
        # even without a metric edit. Keep every non-identity table byte exact.
        from fontTools.ttLib.tables.DefaultTable import DefaultTable
        for tag in font.reader.keys():
            if tag in ('name','head'):continue
            table=DefaultTable(tag);table.data=font.reader[tag];font[tag]=table
        result=BytesIO();font.save(result);return result.getvalue()


def ttf_bytes(style='regular'):
    if style!='regular':raise ConversionError('portable_light_style_unsupported')
    # Always revalidate operator bytes, even after conversion was cached.
    return convert_font(approved_data())


@lru_cache(maxsize=1)
def _cmap(data):
    from fontTools.ttLib import TTFont
    with TTFont(BytesIO(data)) as font:return frozenset(font.getBestCmap())


def approved_cmap():
    return _cmap(ttf_bytes())


def capability(text=None, *, bold=False, italic=False):
    if bold or italic:return False
    try:
        cmap=approved_cmap()
        return text is None or all(ord(c) in cmap for c in text+unicodedata.normalize('NFKC',text))
    except ConversionError:return False
