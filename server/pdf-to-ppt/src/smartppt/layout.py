"""Coordinate-preserving text repair with unchanged raster graphics.

This deliberately keeps unsupported objects as images and reports that limitation.
It never claims that a raster graph is an editable chart.
"""
from collections import defaultdict
from contextlib import closing
import ctypes
from io import BytesIO
import math
import re
import unicodedata
import pypdfium2 as pdfium
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR,MSO_AUTO_SIZE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt


def font_family(name,text):
    if any('\u2e80'<=c<='\uffef' for c in text):
        return 'Noto Sans SC',True
    name=re.sub(r'^[A-Z]{6}\+','',name)
    if any(x in name.lower() for x in ['times','serif','song','roman']):return 'Times New Roman',name!='Times New Roman'
    if 'courier' in name.lower() or 'mono' in name.lower():return 'Courier New',name!='Courier New'
    if name in ['Arial','Helvetica','Helvetica-Bold']:return 'Arial',name!='Arial'
    return 'Arial',name!='Arial'


def add_text(slide,text,x,y,width,height,size,font='Arial',bold=False,color=(0,0,0),scale=1):
    shape=slide.shapes.add_textbox(Pt(x),Pt(y),Pt(max(width,1)),Pt(max(height,1)))
    tf=shape.text_frame;tf.clear();tf.word_wrap=False;tf.auto_size=MSO_AUTO_SIZE.NONE
    tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
    tf.vertical_anchor=MSO_ANCHOR.TOP
    p=tf.paragraphs[0];p.space_before=p.space_after=Pt(0)
    r=p.add_run();r.text=text;r.font.name=font;r.font.size=Pt(max(1,min(size,400)))
    r.font.bold=bold;r.font.color.rgb=RGBColor(*color)
    props=r._r.get_or_add_rPr()
    for tag in ('a:ea','a:cs'):
        el=OxmlElement(tag);el.set('typeface',font);props.append(el)
    if len(text)>1 and abs(scale-1)>.01:
        # OOXML character spacing preserves the PDF advance across a short run.
        spacing=max(-size*.25,min(size*.5,(width-size*.5*len(text))/(len(text)-1)))
        props.set('spc',str(round(spacing*100)))
    return shape


def extract_native(page):
    """Resolve character boxes in page coordinates, retaining object provenance."""
    raw=pdfium.raw;groups=defaultdict(list);objects={};unsupported=[]
    rotation=page.get_rotation();pw,ph=page.get_size()
    def rotate_box(box):
        l,b,r,t=box
        def point(x,y):
            if rotation==90:return y,ph-x
            if rotation==180:return pw-x,ph-y
            if rotation==270:return pw-y,x
            return x,y
        points=[point(x,y) for x,y in [(l,b),(l,t),(r,b),(r,t)]]
        return (min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points))
    with closing(page.get_textpage()) as tp:
        for i in range(tp.count_chars()):
            value=raw.FPDFText_GetUnicode(tp,i)
            if not value or value in (10,13):continue
            obj=tp.get_textobj(i)
            if obj is None:continue
            pointer=ctypes.cast(obj.raw,ctypes.c_void_p).value
            if raw.FPDFTextObj_GetTextRenderMode(obj)==3:continue
            char=chr(value)
            try:
                box=tp.get_charbox(i);size=float(raw.FPDFText_GetFontSize(tp,i))
                matrix=obj.get_matrix();size*=math.hypot(matrix.c,matrix.d)
                angle=(float(raw.FPDFText_GetCharAngle(tp,i))+math.radians(rotation)+math.pi)%(2*math.pi)-math.pi
                box=rotate_box(box)
            except Exception:
                unsupported.append('unresolved_character');continue
            if not all(math.isfinite(n) for n in (*box,size,angle)) or not 0<size<500:continue
            objects[pointer]=obj
            groups[pointer].append({'text':char,'box':box,'size':size,'angle':angle,'index':i})
        runs=[];remove=[]
        for pointer,chars in groups.items():
            obj=objects[pointer]
            if any(abs(c['angle'])>.01 or (unicodedata.category(c['text'])=='Cc' and not c['text'].isspace()) for c in chars):
                unsupported.append('rotated_text_kept_as_graphic');continue
            font=obj.get_font();name=font.get_family_name();bold=font.get_weight()>=600 or 'bold' in font.get_base_name().lower()
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
                size=pending[0]['size'];family,substituted=font_family(name,text)
                runs.append({'text':text,'box':[l,b,r,t],'size':size,'font':family,
                    'substituted':substituted,'source_font':name,'bold':bold,'color':rgb,'index':pending[0]['index']})
            for char in chars:
                if pending:
                    previous=pending[-1];size=char['size']
                    gap=char['box'][0]-previous['box'][2]
                    if abs(char['box'][1]-previous['box'][1])>size*.45 or gap>size*.8 or gap < -size:
                        flush();pending=[]
                pending.append(char)
            flush();remove.append(obj)
        runs.sort(key=lambda r:r['index'])
        return runs,remove,sorted(set(unsupported))


def page_background(page,remove,max_side=1800):
    for obj in remove:
        if not pdfium.raw.FPDFPageObj_SetIsActive(obj,False):raise RuntimeError('cannot remove native text')
    try:
        with closing(page.render(scale=min(2.5,max_side/max(page.get_size())))) as bitmap:
            image=bitmap.to_pil().convert('RGB').copy()
    finally:
        for obj in remove:pdfium.raw.FPDFPageObj_SetIsActive(obj,True)
    return image


def add_background(slide,image,width,height,offset=(0,0)):
    stream=BytesIO();image.save(stream,format='PNG');stream.seek(0)
    slide.shapes.add_picture(stream,Pt(offset[0]),Pt(offset[1]),width=Pt(width),height=Pt(height))


def native_slide(prs,page,slide=None):
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    runs,remove,warnings=extract_native(page)
    slide=slide if slide is not None else prs.slides.add_slide(prs.slide_layouts[6])
    add_background(slide,page_background(page,remove),w*scale,h*scale,(ox,oy))
    for run in runs:
        l,b,r,t=run['box'];fs=run['size']
        add_text(slide,run['text'],ox+l*scale,oy+(h-t-fs*.18)*scale,
            (r-l+fs*.3)*scale,fs*1.5*scale,fs*scale,run['font'],run['bold'],run['color'])
    return {'route':'native-coordinate','editable_runs':len(runs),'font_substitutions':sorted(set(r['source_font']+' → '+r['font'] for r in runs if r['substituted'])),
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
