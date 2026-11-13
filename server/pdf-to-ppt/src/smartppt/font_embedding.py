"""Embed only pinned, openly licensed font faces as complete EOT fonts.

System fonts and arbitrary fonts from uploaded PDFs are never redistributed.
The whole static face is retained so recipients can type new characters.
"""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from collections import defaultdict
from copy import deepcopy
import os
import json
import struct
import unicodedata
import zipfile
from lxml import etree as ET
from .config import ConversionError

NOTO_SHA256='a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da'
SERIF_SHA256='050080d9255a86808f2945bffac582b31ef32bc36411ce29563b4961670c66f9'
FAMILIES={'Noto Sans SC':('SMARTPPT_CJK_FONT','NotoSansSC-variable.ttf',NOTO_SHA256,'OFL-NotoSansSC.txt'),
          'Noto Serif SC':('SMARTPPT_CJK_SERIF_FONT','NotoSerifSC-variable.ttf',SERIF_SHA256,'OFL-NotoSerifSC.txt')}
FAMILIES['SmartPDF Sans100']=FAMILIES['Noto Sans SC']
FAMILIES['SmartPDF Serif200']=FAMILIES['Noto Serif SC']
CMU_FACES=json.loads(Path(__file__).with_name('cmu-fonts.json').read_text())['families']
PORTABLE_FAMILIES=set(FAMILIES)|set(CMU_FACES)
STYLES=('regular','bold','italic','boldItalic')
P='http://schemas.openxmlformats.org/presentationml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'


def separate_unicode_aliases(font):
    """Retain every character, with distinct glyph IDs for Unicode aliases.

    PowerPoint's PDF exporter can reverse a shared glyph to the wrong character
    (e.g. 长 becomes the radical ⻓). Duplicate outlines/metrics for aliases;
    keep the unified ideograph's original glyph and shaping behavior.
    """
    aliases=defaultdict(list)
    for code,glyph in font.getBestCmap().items():aliases[glyph].append(code)
    # glyf.__setitem__ also appends to its order; keep our explicit order separate.
    order=list(font.getGlyphOrder())
    for glyph,codes in aliases.items():
        unified=[c for c in codes if unicodedata.name(chr(c),'').startswith('CJK UNIFIED IDEOGRAPH-')]
        primary=min(unified or codes)
        for code in codes:
            if code==primary:continue
            name=f'smartU{code:06X}'
            if name in font['glyf'] or len(order)>=65535:raise ConversionError('portable_font_glyph_limit')
            font['glyf'][name]=deepcopy(font['glyf'][glyph]);font['hmtx'].metrics[name]=font['hmtx'].metrics[glyph]
            if 'vmtx' in font:font['vmtx'].metrics[name]=font['vmtx'].metrics[glyph]
            order.append(name)
            for table in font['cmap'].tables:
                if table.isUnicode() and code in getattr(table,'cmap',{}):table.cmap[code]=name
    font.setGlyphOrder(order)


def eot_payload(font,data):
    """Uncompressed EOT 0x00020001, with actual names and embedding rights."""
    os2=font['OS/2']
    if os2.fsType!=0:raise ConversionError('portable_font_license_not_installable')
    keys=('bFamilyType','bSerifStyle','bWeight','bProportion','bContrast','bStrokeVariation','bArmStyle','bLetterForm','bMidline','bXHeight')
    header=struct.pack('<IIII',0,len(data),0x00020001,0)+bytes(getattr(os2.panose,k) for k in keys)
    header+=struct.pack('<BBIHH',1,os2.fsSelection&1,os2.usWeightClass,os2.fsType,0x504c)
    header+=struct.pack('<IIIIIII',*[getattr(os2,'ulUnicodeRange'+str(i)) for i in range(1,5)],
                        os2.ulCodePageRange1,os2.ulCodePageRange2,font['head'].checkSumAdjustment)+b'\0'*16
    for name_id in (1,2,5,4):
        name=font['name'].getDebugName(name_id)
        if not name:raise ConversionError('portable_font_names_missing')
        encoded=name.encode('utf-16le')
        if len(encoded)>65535:raise ConversionError('portable_font_names_invalid')
        header+=struct.pack('<HH',0,len(encoded))+encoded
    header+=b'\0'*4  # padding and an empty root string; OFL permits distribution.
    return struct.pack('<I',len(header)+len(data))+header[4:]+data


@lru_cache(maxsize=8)
def noto_payload(data,bold=False,family='Noto Sans SC'):
    if family not in FAMILIES or sha256(data).hexdigest()!=FAMILIES[family][2]:raise ConversionError('portable_font_integrity_failed')
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    with TTFont(BytesIO(data)) as font:
        font=instantiateVariableFont(font,{'wght':700 if bold else {'SmartPDF Sans100':100,'SmartPDF Serif200':200}.get(family,400)},inplace=True,updateFontNames=True)
        if family in ('SmartPDF Sans100','SmartPDF Serif200'):
            # A distinct family/PostScript identity prevents the variable face
            # from replacing this approved static weight in Office/fontconfig.
            style='Bold' if bold else 'Regular'
            for record in list(font['name'].names):
                if record.nameID in (1,16):value=family
                elif record.nameID in (2,17):value=style
                elif record.nameID==4:value=family+' '+style
                elif record.nameID in (3,6):value=family.replace(' ','')+'-'+style
                else:continue
                font['name'].setName(value,record.nameID,record.platformID,record.platEncID,record.langID)
        separate_unicode_aliases(font)
        # Carry the complete copyright/license notice inside the font metadata,
        # so it survives Office editing and repackaging of the presentation.
        license_text=Path(__file__).with_name(FAMILIES[family][3]).read_text()
        font['name'].setName(license_text,13,3,1,0x409)
        output=BytesIO();font.save(output)
        return eot_payload(font,output.getvalue())


@lru_cache(maxsize=12)
def cmu_payload(data,family,style):
    expected=CMU_FACES.get(family,{}).get(style,{})
    if sha256(data).hexdigest()!=expected.get('sha256'):raise ConversionError('portable_font_integrity_failed')
    from fontTools.ttLib import TTFont
    with TTFont(BytesIO(data)) as font:
        separate_unicode_aliases(font)
        font['name'].setName(Path(__file__).with_name('OFL-CMU.txt').read_text(),13,3,1,0x409)
        output=BytesIO();font.save(output)
        return eot_payload(font,output.getvalue())


def bundled_payloads(bold=False,family='Noto Sans SC',styles=None):
    if family in CMU_FACES:
        root=Path(os.getenv('SMARTPPT_CMU_FONT_DIR','cmu-fonts'))
        required=set(styles or ())|{'regular'}|({'bold'} if bold else set());result={}
        if required-set(STYLES):raise ConversionError('portable_font_integrity_failed')
        for style in STYLES:
            if style not in required:continue
            path=root/CMU_FACES[family][style]['file']
            if not path.is_file() or path.stat().st_size>4*1024*1024:raise ConversionError('portable_font_unavailable')
            result[style]=cmu_payload(path.read_bytes(),family,style)
        return result
    if family not in FAMILIES:raise ConversionError('portable_font_integrity_failed')
    env,filename,_,_=FAMILIES[family];path=Path(os.getenv(env,filename))
    if not path.is_file() or path.stat().st_size>32*1024*1024:raise ConversionError('portable_font_unavailable')
    data=path.read_bytes();result={'regular':noto_payload(data,family=family)}
    if bold:result['bold']=noto_payload(data,True,family)
    return result


def embed_noto(source,target,payloads,family='Noto Sans SC'):
    """Add one unique, used typeface and collision-free package relationships."""
    with zipfile.ZipFile(source) as package:parts={n:package.read(n) for n in package.namelist()}
    parser=ET.XMLParser(resolve_entities=False,no_network=True)
    root=ET.fromstring(parts['ppt/presentation.xml'],parser)
    if family not in PORTABLE_FAMILIES:raise ConversionError('portable_font_integrity_failed')
    if not any(family.encode() in data for name,data in parts.items() if name.startswith('ppt/slides/') and name.endswith('.xml')):
        raise ConversionError('portable_font_not_used')
    fonts=root.find('{'+P+'}embeddedFontLst')
    if fonts is None:
        fonts=ET.Element('{'+P+'}embeddedFontLst')
        # The presentation schema places the font list before these siblings.
        later={'custShowLst','photoAlbum','custDataLst','kinsoku','defaultTextStyle','extLst'}
        index=next((i for i,node in enumerate(root) if ET.QName(node).localname in later),len(root));root.insert(index,fonts)
    if any(f.find('{'+P+'}font').get('typeface')==family for f in fonts if f.find('{'+P+'}font') is not None):
        raise ConversionError('portable_font_already_embedded')
    entry=ET.SubElement(fonts,'{'+P+'}embeddedFont');ET.SubElement(entry,'{'+P+'}font',typeface=family)
    rels=ET.fromstring(parts['ppt/_rels/presentation.xml.rels'],parser);types=ET.fromstring(parts['[Content_Types].xml'],parser)
    ids={r.get('Id') for r in rels};index=1
    for style in STYLES:
        if style not in payloads:continue
        while f'rIdSmartFont{index}' in ids or f'ppt/fonts/smart-noto-{index}.fntdata' in parts:index+=1
        rid=f'rIdSmartFont{index}';name=f'ppt/fonts/smart-noto-{index}.fntdata';ids.add(rid)
        ET.SubElement(entry,'{'+P+'}'+style,{'{'+R+'}id':rid})
        ET.SubElement(rels,'{'+REL+'}Relationship',Id=rid,Type=R+'/font',Target=name.removeprefix('ppt/'))
        ET.SubElement(types,'{'+CT+'}Override',PartName='/'+name,ContentType='application/x-fontdata');parts[name]=payloads[style]
    root.set('embedTrueTypeFonts','1');root.set('saveSubsetFonts','0')
    for name,xml in [('ppt/presentation.xml',root),('ppt/_rels/presentation.xml.rels',rels),('[Content_Types].xml',types)]:
        parts[name]=ET.tostring(xml,xml_declaration=True,encoding='UTF-8',standalone=True)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as package:
        for name,data in parts.items():package.writestr(name,data)
