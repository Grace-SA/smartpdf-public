"""Coordinate-preserving text repair with unchanged raster graphics.

This deliberately keeps unsupported objects as images and reports that limitation.
It never claims that a raster graph is an editable chart.
"""
from collections import defaultdict
from contextlib import closing
import ctypes
from io import BytesIO
import math
import os
from pathlib import Path
import re
import unicodedata
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR,MSO_AUTO_SIZE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt


def modern_face(name):
    """Resolve named TeX/CMU faces without guessing unknown symbol fonts."""
    name=re.sub(r'^[A-Z]{6}\+','',name).lower().replace(' ','')
    for pattern,family in ((r'cmuserif(?:[-,](?:roman|regular|bold|italic|bolditalic))?','CMU Serif'),
                           (r'cmusansserif(?:[-,](?:medium|regular|bold|oblique|boldoblique))?','CMU Sans Serif'),
                           (r'cmutypewritertext(?:[-,](?:regular|bold|italic|bolditalic))?','CMU Typewriter Text'),
                           (r'cm(?:r|bx|b|ti|sl)\d+(?:[-,].*)?','CMU Serif'),
                           (r'cmss(?:bx|i)?\d+(?:[-,].*)?','CMU Sans Serif'),
                           (r'cmtt\d+(?:[-,].*)?','CMU Typewriter Text'),
                           # CM-Super explicit shape codes; exclude small caps,
                           # variable-width, bright and unknown variants.
                           (r'sf(?:rm|sl|ti|bx|bl|bi|rb)\d{4}','CMU Serif'),
                           (r'sf(?:ss|si|sx|so)\d{4}','CMU Sans Serif'),
                           (r'sf(?:tt|st|it)\d{4}','CMU Typewriter Text')):
        if re.fullmatch(pattern,name):return family
    return None


def graphical_font(name):
    """Preserve formula/symbol glyphs instead of trusting their text encoding."""
    name=re.sub(r'^[A-Z]{6}\+','',name).lower().replace(' ','')
    return (bool(re.fullmatch(r'(?:cmmi|cmsy|cmex|msam|msbm|rsfs|eufm|eufb|eurm|eusb|eusm|euex)\d+',name))
            or any(k in name for k in ('wingdings','zapfdingbats','cambria-math','cambriamath','stixmath'))
            or name in ('symbol','symbolmt'))


def graphical_text(name,text):
    # Unicode bullets and basic unit symbols have ordinary text equivalents.
    # Do not turn a correct paragraph into a raster because its bullets use
    # Symbol. Arbitrary formula glyphs and private-use encodings stay graphic.
    return graphical_font(name) and any(c not in ' •µμ×.\t\r\n' for c in text)


def cjk_text(text):
    # Latin ligatures (FB00-FB06) and private-use glyphs are not Chinese.
    ranges=((0x2E80,0x2FFF),(0x3000,0x312F),(0x31A0,0x31BF),(0x31F0,0x31FF),
            (0x3400,0x4DBF),(0x4E00,0x9FFF),(0xF900,0xFAFF),(0xFE10,0xFE1F),
            (0xFE30,0xFE4F),(0xFF00,0xFFEF),(0x20000,0x323AF))
    return any(any(a<=ord(c)<=b for a,b in ranges) for c in text)


def font_family(name,text,flags=0,base_name=None):
    from .termes_font import source_family
    termes=source_family(base_name or name)
    if termes and not cjk_text(text):return termes,True
    modern=modern_face(base_name or name);directory=os.getenv('SMARTPPT_CMU_FONT_DIR')
    if modern and directory and not cjk_text(text):
        files={'CMU Serif':'cmunrm.ttf','CMU Sans Serif':'cmunss.ttf','CMU Typewriter Text':'cmuntt.ttf'}
        if (Path(directory)/files[modern]).is_file():return modern,name!=modern
    # Keep the Latin letters of a named CJK serif face in that same family.
    # Opt in only when the operator actually provides the optional font.
    lower=re.sub(r'^[A-Z]{6}\+','',name).lower().replace(' ','')
    serif_path=os.getenv('SMARTPPT_CJK_SERIF_FONT')
    if serif_path and Path(serif_path).is_file() and any(k in lower for k in ('songti','simsun','nsimsun','sung','mingliu','notoserifsc','宋体','明體')):
        return 'Noto Serif SC',name!='Noto Serif SC'
    if cjk_text(text):
        return 'Noto Sans SC',True
    name=re.sub(r'^[A-Z]{6}\+','',name)
    # Known families take precedence over unreliable descriptor flags. In
    # particular, HelveticaNeue-Roman is sans serif despite its style suffix.
    lower=name.lower().replace(' ','')
    if lower.startswith(('arial','helvetica','nimbussans')):return 'Arial',name!='Arial'
    if lower.startswith(('times','nimbusroman')):return 'Times New Roman',name!='Times New Roman'
    if lower.startswith(('courier','nimbusmono')):return 'Courier New',name!='Courier New'
    if flags & 1:return 'Courier New',name!='Courier New'
    if flags & 2:return 'Times New Roman',name!='Times New Roman'
    if any(x in name.lower() for x in ['times','serif','song','roman']):return 'Times New Roman',name!='Times New Roman'
    if 'courier' in name.lower() or 'mono' in name.lower():return 'Courier New',name!='Courier New'
    if name in ['Arial','Helvetica','Helvetica-Bold']:return 'Arial',name!='Arial'
    return 'Arial',name!='Arial'


def font_style(base_name,weight,flags=0):
    """Prefer explicit face names over PDFium's stem-width weight estimate."""
    name=re.sub(r'^[A-Z]{6}\+','',base_name).lower().replace(' ','')
    from .termes_font import face_name
    termes=face_name(base_name)
    if termes:return termes in ('bold','boldItalic'),termes in ('italic','boldItalic')
    if modern_face(base_name):
        if name.startswith('sf'):
            shape=name[2:4]
            return shape in {'bx','bl','bi','rb','sx','so'},shape in {'sl','ti','bl','bi','si','so','st','it'}
        if name.startswith('cmu'):return 'bold' in name,any(s in name for s in ('italic','oblique'))
        return name.startswith(('cmb','cmssbx')),name.startswith(('cmti','cmsl','cmmi','cmssi'))
    italic=bool(flags & 64) or any(x in name for x in ('italic','oblique'))
    if any(x in name for x in ('bold','semibold','demi','heavy','black')):return True,italic
    regular_faces={'helvetica','helvetica-oblique','times-roman','times-italic','courier','courier-oblique',
                   'arial','arialmt','arial-italicmt','timesnewromanpsmt','timesnewromanps-italicmt',
                   'couriernewpsmt','couriernewps-italicmt'}
    if name in regular_faces or re.search(r'(?:-|,)(?:regular|roman|book|light|thin)(?:italic|oblique)?$',name):
        return False,italic
    return weight>=600,italic


def add_text(slide,text,x,y,width,height,size,font='Arial',bold=False,color=(0,0,0),scale=1,italic=False):
    shape=slide.shapes.add_textbox(Pt(x),Pt(y),Pt(max(width,1)),Pt(max(height,1)))
    tf=shape.text_frame;tf.clear();tf.word_wrap=False;tf.auto_size=MSO_AUTO_SIZE.NONE
    tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
    tf.vertical_anchor=MSO_ANCHOR.TOP
    p=tf.paragraphs[0];p.space_before=p.space_after=Pt(0)
    r=p.add_run();r.text=text;r.font.name=font;r.font.size=Pt(max(1,min(size,400)))
    r.font.bold=bold;r.font.italic=italic;r.font.color.rgb=RGBColor(*color)
    props=r._r.get_or_add_rPr()
    for tag in ('a:ea','a:cs'):
        el=OxmlElement(tag);el.set('typeface',font);props.append(el)
    if len(text)>1 and abs(scale-1)>.01:
        # OOXML character spacing preserves the PDF advance across a short run.
        spacing=max(-size*.25,min(size*.5,(width-size*.5*len(text))/(len(text)-1)))
        props.set('spc',str(round(spacing*100)))
    return shape


def extract_native(page, *, split_words=False, allow_quarter_turns=False, partial_regions=False):
    """Resolve character boxes in page coordinates, retaining object provenance."""
    if partial_regions and not split_words:raise ValueError('partial regions require word isolation')
    raw=pdfium.raw;groups=defaultdict(list);objects={};unsupported=[];incomplete=set();clipped=set()
    rotation=page.get_rotation();pw,ph=page.get_size()
    # PDFium text coordinates are in the original page coordinate system;
    # rendered pages start at the effective CropBox/MediaBox intersection.
    origin_x,origin_y,_,_=page.get_bbox()
    def rotate_box(box):
        l,b,r,t=box
        def point(x,y):
            x-=origin_x;y-=origin_y
            if rotation==90:return y,ph-x
            if rotation==180:return pw-x,ph-y
            if rotation==270:return pw-y,x
            return x,y
        points=[point(x,y) for x,y in [(l,b),(l,t),(r,b),(r,t)]]
        return (min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points))
    with closing(page.get_textpage()) as tp:
        for i in range(tp.count_chars()):
            value=raw.FPDFText_GetUnicode(tp,i)
            obj=tp.get_textobj(i)
            if obj is None:continue
            pointer=ctypes.cast(obj.raw,ctypes.c_void_p).value
            if raw.FPDFTextObj_GetTextRenderMode(obj)==3:continue
            if not value or value in (10,13):
                incomplete.add(pointer);continue
            char=chr(value)
            try:
                box=tp.get_charbox(i);size=float(raw.FPDFText_GetFontSize(tp,i))
                matrix=raw.FS_MATRIX()
                transform_index=i
                if char.isspace() and raw.FPDFText_IsGenerated(tp,i)==1:
                    # PDFium inserts spaces for positioned glyph gaps, with an
                    # identity matrix even when the text object is scaled.
                    # Only inherit an adjacent real glyph in this same object;
                    # an object matrix alone would omit enclosing form transforms.
                    neighbors=[]
                    for neighbor in (i-1,i+1):
                        if not 0<=neighbor<tp.count_chars() or raw.FPDFText_IsGenerated(tp,neighbor)!=0:continue
                        adjacent=tp.get_textobj(neighbor)
                        if adjacent is not None and ctypes.cast(adjacent.raw,ctypes.c_void_p).value==pointer:
                            neighbors.append(neighbor)
                    if not neighbors:raise ValueError('generated space has no adjacent source glyph')
                    transform_index=neighbors[0]
                    size=float(raw.FPDFText_GetFontSize(tp,transform_index))
                if not raw.FPDFText_GetMatrix(tp,transform_index,ctypes.byref(matrix)):raise ValueError('missing effective character transform')
                horizontal=math.hypot(matrix.a,matrix.b);det=matrix.a*matrix.d-matrix.b*matrix.c
                if horizontal<=0 or det<=0:raise ValueError('mirrored or degenerate text transform')
                size*=det/horizontal
                shear=(matrix.a*matrix.c+matrix.b*matrix.d)/det
                # CharAngle uses atan2(c,a), which mistakes synthetic italic
                # shear for baseline rotation. The horizontal basis is (a,b).
                angle=(-math.atan2(matrix.b,matrix.a)+math.radians(rotation)+math.pi)%(2*math.pi)-math.pi
                box=rotate_box(box)
                loose=raw.FS_RECTF();advance_box=None
                if raw.FPDFText_GetLooseCharBox(tp,i,ctypes.byref(loose)):
                    candidate=rotate_box((loose.left,loose.bottom,loose.right,loose.top))
                    if all(math.isfinite(v) for v in candidate):advance_box=candidate
            except Exception:
                unsupported.append('unresolved_character');incomplete.add(pointer);continue
            if not all(math.isfinite(n) for n in (*box,size,angle)) or not 0<size<500:
                incomplete.add(pointer);continue
            if not char.isspace() and (box[0]<0 or box[1]<0 or box[2]>pw or box[3]>ph):
                clipped.add(pointer)
            objects[pointer]=obj
            origin_x_value,origin_y_value=ctypes.c_double(),ctypes.c_double()
            baseline=None;baseline_point=None
            if raw.FPDFText_GetCharOrigin(tp,transform_index,origin_x_value,origin_y_value) and all(math.isfinite(v.value) for v in (origin_x_value,origin_y_value)):
                baseline_point=rotate_box((origin_x_value.value,origin_y_value.value,origin_x_value.value,origin_y_value.value))[:2]
                baseline=baseline_point[1]
            # Group glyphs along the text's own baseline, including quarter
            # turns. Page-space boxes remain authoritative for reconstruction.
            l,b,r,t=box;c,s=math.cos(angle),math.sin(angle)
            pts=[(x*c+y*s,-x*s+y*c) for x,y in [(l,ph-t),(r,ph-t),(r,ph-b),(l,ph-b)]]
            line_box=(min(x for x,y in pts),-max(y for x,y in pts),max(x for x,y in pts),-min(y for x,y in pts))
            line_baseline=baseline_point[0]*s-(ph-baseline_point[1])*c if baseline_point is not None else None
            groups[pointer].append({'text':char,'box':box,'advance_box':advance_box,'line_box':line_box,'line_baseline':line_baseline,'size':size,'angle':angle,'shear':shear,'index':i,'baseline':baseline})
        runs=[];remove=[]
        for pointer,chars in groups.items():
            obj=objects[pointer]
            # Only opaque fill-only objects can be reproduced by add_text.
            # Stroke and clipping modes have effects beyond their glyph boxes.
            if raw.FPDFTextObj_GetTextRenderMode(obj)!=0:
                unsupported.append('text_paint_mode_kept_as_graphic');continue
            paint=[ctypes.c_uint() for _ in range(4)]
            if not raw.FPDFPageObj_GetFillColor(obj,*paint) or paint[3].value!=255:
                unsupported.append('transparent_text_kept_as_graphic');continue
            if graphical_text(obj.get_font().get_base_name(),''.join(c['text'] for c in chars)):
                unsupported.append('formula_or_symbol_font_kept_as_graphic');continue
            # Removing an entire text object would also remove its clipped
            # glyphs. Keep that object in the raster instead of reconstructing
            # off-page text which was not visible in the source.
            if pointer in clipped:
                unsupported.append('clipped_text_kept_as_graphic');continue
            # Deactivating a PDF text object removes ALL of its glyphs. Never
            # remove one if even one of its characters could not be resolved.
            if pointer in incomplete:
                unsupported.append('incomplete_text_object_kept_as_graphic');continue
            def unsupported_angle(angle):
                return abs(angle-round(angle/(math.pi/2))*(math.pi/2))>.01 if allow_quarter_turns else abs(angle)>.01
            if any(unsupported_angle(c['angle']) for c in chars):
                unsupported.append('rotated_text_kept_as_graphic');continue
            shears=[c['shear'] for c in chars]
            if any(abs(x)>.03 and not .10<=x<=.36 for x in shears):
                unsupported.append('unsupported_text_shear_kept_as_graphic');continue
            ambiguous=[c for c in chars if unicodedata.category(c['text']) in ('Cc','Co') and not c['text'].isspace()]
            if ambiguous:
                unsupported.append('unmapped_glyph_kept_as_graphic')
                # Full-object reconstruction is still forbidden. The regional
                # path alone can copy isolated word rectangles from a scratch
                # render while retaining these exact glyphs in the source image.
                if not partial_regions:continue
                if any(c['box'][2]<=c['box'][0] or c['box'][3]<=c['box'][1] for c in ambiguous):continue
            blocked_boxes=[c['box'] for c in ambiguous]
            font=obj.get_font();name=font.get_family_name()
            flags=max(0,raw.FPDFFont_GetFlags(font))
            bold,italic=font_style(font.get_base_name(),font.get_weight(),flags)
            italic=italic or any(x>=.10 for x in shears)
            color=[ctypes.c_uint() for _ in range(4)]
            ok=raw.FPDFPageObj_GetFillColor(obj,*color)
            rgb=tuple(c.value for c in color[:3]) if ok else (0,0,0)
            pending=[]
            def flush():
                if not pending:return
                text=''.join(c['text'] for c in pending).encode('utf-16','surrogatepass').decode('utf-16','replace')
                visible=[c for c in pending if not c['text'].isspace()]
                if not visible:return
                l=min(c['box'][0] for c in visible);b=min(c['box'][1] for c in visible)
                r=max(c['box'][2] for c in visible);t=max(c['box'][3] for c in visible)
                size=pending[0]['size'];family,substituted=font_family(name,text,flags,base_name=font.get_base_name())
                from .base_font import source_family
                exact_family=source_family(font,text,bold=bold,italic=italic)
                if exact_family is not None:family,substituted=exact_family,True
                runs.append({'text':text,'box':[l,b,r,t],'size':size,'font':family,
                    'substituted':substituted,'source_font':name,'bold':bold,'color':rgb,'index':pending[0]['index'],
                    'end_index':pending[-1]['index']+1,'source_base_font':font.get_base_name(),
                    'object_id':pointer,'italic':italic,'baseline':pending[0]['baseline'],
                    'blocked_boxes':blocked_boxes,
                    'advance_box':([min(c['advance_box'][0] for c in visible),min(c['advance_box'][1] for c in visible),
                                    max(c['advance_box'][2] for c in visible),max(c['advance_box'][3] for c in visible)]
                                   if all(c['advance_box'] is not None for c in visible) else None),
                    'rotation':(round(math.degrees(pending[0]['angle'])/90)*90)%360})
            for char in chars:
                if unicodedata.category(char['text']) in ('Cc','Co') and not char['text'].isspace():
                    flush();pending=[];continue
                if split_words and char['text'].isspace():
                    pending.append(char);flush();pending=[];continue
                if pending:
                    previous=pending[-1];size=char['size']
                    gap=char['line_box'][0]-previous['line_box'][2]
                    # Quotes and descenders have different ink bottoms on the
                    # same baseline. Use the source origin when it is known;
                    # otherwise keep the conservative ink-bound fallback.
                    a,b=char['line_baseline'],previous['line_baseline']
                    different_line=abs(a-b)>size*.2 if a is not None and b is not None else abs(char['line_box'][1]-previous['line_box'][1])>size*.45
                    if different_line or abs(char['size']-previous['size'])>size*.05 or gap>size*.8 or gap < -size:
                        flush();pending=[]
                pending.append(char)
            flush();remove.append(obj)
        runs.sort(key=lambda r:r['index'])
        return runs,remove,sorted(set(unsupported))


def page_background(page,remove,max_side=1800,scale_limit=2.5):
    disabled=[]
    try:
        for obj in remove:
            if not pdfium.raw.FPDFPageObj_SetIsActive(obj,False):raise RuntimeError('cannot remove native text')
            disabled.append(obj)
        with closing(page.render(scale=min(scale_limit,max_side/max(page.get_size())))) as bitmap:
            image=bitmap.to_pil().convert('RGB').copy()
    finally:
        for obj in disabled:pdfium.raw.FPDFPageObj_SetIsActive(obj,True)
    return image


def add_background(slide,image,width,height,offset=(0,0)):
    stream=BytesIO();image.save(stream,format='PNG');stream.seek(0)
    slide.shapes.add_picture(stream,Pt(offset[0]),Pt(offset[1]),width=Pt(width),height=Pt(height))


def merge_native_runs(page,runs):
    """Join adjacent source glyph objects without crossing columns or styles.

    PDFium-generated spaces have no text object. Recover only those literal
    whitespace gaps from the source text stream; never invent or reorder text.
    Object removal/provenance stays in extract_native, before this presentation
    grouping. Regional all-or-nothing object verification remains unchanged.
    """
    result=[]
    with closing(page.get_textpage()) as tp:
        for run in runs:
            item=dict(run);item['object_ids']=[run['object_id']];previous=result[-1] if result else None
            if previous:
                a,b=previous['box'],run['box'];size=run['size'];gap=run['index']-previous['end_index']
                compatible=(0<=gap<=8 and abs(previous['size']-size)<.01
                            and all(previous[k]==run[k] for k in ('font','source_font','source_base_font','bold','italic','color'))
                            and previous['baseline'] is not None and run['baseline'] is not None
                            and abs(previous['baseline']-run['baseline'])<=size*.08
                            and -.1*size<=b[0]-a[2]<=size*.8)
                if compatible:
                    separator=tp.get_text_range(previous['end_index'],gap) if gap else ''
                    generated_breaks=all(raw_value in (9,10,13,32) and
                                         (raw_value not in (10,13) or pdfium.raw.FPDFText_IsGenerated(tp,j)==1)
                                         for j in range(previous['end_index'],run['index'])
                                         for raw_value in [pdfium.raw.FPDFText_GetUnicode(tp,j)])
                    if generated_breaks and all(c in ' \t\r\n' for c in separator):
                        had_break='\r' in separator or '\n' in separator
                        separator=separator.replace('\r','').replace('\n','')
                        # Some producers position each glyph separately; PDFium
                        # reports artificial newlines even on a shared baseline.
                        if had_break and not separator:
                            left=previous.get('advance_box');right=run.get('advance_box')
                            gap_width=right[0]-left[2] if left is not None and right is not None else b[0]-a[2]
                            if gap_width>size*.22:separator=' '
                        previous['text']+=separator+run['text'];previous['end_index']=run['end_index']
                        previous['object_ids'].append(run['object_id'])
                        left=previous.get('advance_box');right=run.get('advance_box')
                        previous['advance_box']=([min(left[0],right[0]),min(left[1],right[1]),max(left[2],right[2]),max(left[3],right[3])]
                                                 if left is not None and right is not None else None)
                        previous['box']=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]
                        continue
            result.append(item)
    return result


def reference_text(page,original):
    """Repair whitespace boundaries only when every source character agrees.

    This is source geometry, not OCR truth. Missing/hidden/clipped characters
    cannot be filled in or silently removed to make content checks pass.
    """
    from .quality import normalized
    try:
        runs,_,_=extract_native(page)
        candidate='\n'.join(r['text'] for r in merge_native_runs(page,runs))
        return candidate if normalized(candidate)==normalized(original) else original
    except Exception:
        # Optional layout-aware boundaries must not change input eligibility.
        return original


def native_slide(prs,page,slide=None):
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    runs,remove,warnings=extract_native(page)
    source_runs=len(runs);runs=merge_native_runs(page,runs)
    slide=slide if slide is not None else prs.slides.add_slide(prs.slide_layouts[6])
    add_background(slide,page_background(page,remove),w*scale,h*scale,(ox,oy))
    for run in runs:
        l,b,r,t=run['box'];fs=run['size']
        add_text(slide,run['text'],ox+l*scale,oy+(h-t-fs*.18)*scale,
            (r-l+fs*.3)*scale,fs*1.5*scale,fs*scale,run['font'],run['bold'],run['color'],italic=run['italic'])
    return {'route':'native-coordinate','editable_runs':len(runs),'source_object_runs':source_runs,'font_substitutions':sorted(set(r['source_font']+' → '+r['font'] for r in runs if r['substituted'])),
        'warnings':warnings,'graphics':'raster; not editable','source_text_characters':sum(len(r['text']) for r in runs)}


def convert_native(source,target):
    with pdfium.PdfDocument(source) as doc:
        prs=Presentation();w,h=doc.get_page_size(0)
        prs.slide_width=Pt(max(72,min(w,4032)));prs.slide_height=Pt(max(72,min(h,4032)))
        report=[]
        for i in range(len(doc)):
            with closing(doc[i]) as page:report.append(native_slide(prs,page))
        prs.save(target)
    return report

