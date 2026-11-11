"""Opt-in postprocessor: keep verified simple tables; repair geometry; OCR scans.

Always requires review. OCR confidence is not a correctness guarantee.
"""
from contextlib import closing
import hashlib,json,math,os,subprocess,tempfile
import re
from html import unescape
from copy import deepcopy
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image,ImageFont
import pypdfium2 as pdfium
from pptx import Presentation
from .config import ConversionError
from .layout import add_background,add_text,font_family,native_slide
from .pdf import render_page
from .quality import normalized,numeric_tokens,shape_text,text_metrics
from .consensus import region_agreement,overlapping_lines,erase_bounds
from .ocr_font import latin_font


def scan_page(page):
    raw=pdfium.raw
    images=list(page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE]))
    if not images:return False
    with closing(page.get_textpage()) as tp:
        visible=0
        for i in range(tp.count_chars()):
            obj=tp.get_textobj(i)
            if obj and raw.FPDFTextObj_GetTextRenderMode(obj)!=3:visible+=1
    return visible<12


def safe_table(slide,reference):
    tables=[s for s in slide.shapes if s.has_table]
    if not tables:return False
    text='\n'.join(shape_text(slide.shapes));metrics=text_metrics(reference,text)
    if metrics['character_recall']!=1 or metrics['character_precision']!=1:return False
    if numeric_tokens(reference)!=numeric_tokens(text):return False
    # A character/number multiset cannot bind a value to its row or label.
    # Ambiguous extraction order must use coordinate repair and render validation,
    # not bypass those gates by preserving an unverified native table.
    if normalized(reference)!=normalized(text):return False
    sw,sh=slide.part.package.presentation_part.presentation.slide_width,slide.part.package.presentation_part.presentation.slide_height
    return all(s.left>=0 and s.top>=0 and s.left+s.width<=sw+12700 and s.top+s.height<=sh+12700 for s in tables)


def validate_ocr(record,image):
    if record.get('input_sha256')!=hashlib.sha256(image.read_bytes()).hexdigest():raise ConversionError('ocr_provenance_mismatch')
    with Image.open(image) as im:w,h=im.size
    if record.get('image_size')!=[w,h]:raise ConversionError('ocr_geometry_mismatch')
    if len(record.get('lines',[]))>3000:raise ConversionError('ocr_output_limit')
    for line in record['lines']:
        points=line.get('polygon',[])
        if (len(points)!=4 or any(len(p)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in p) for p in points)
            or any(not 0<=p[0]<=w or not 0<=p[1]<=h for p in points)
            or not isinstance(line.get('text'),str) or len(line['text'])>10000
            or not isinstance(line.get('confidence'),(int,float)) or not 0<=line['confidence']<=1):
            raise ConversionError('invalid_ocr_geometry')


def verify_agreement(record,verifier,image):
    validate_ocr(record,image)
    if verifier.get('input_sha256')!=record['input_sha256']:raise ConversionError('ocr_provenance_mismatch')
    if verifier.get('capped'):return False
    text='\n'.join(unescape(re.sub('<[^>]+>',' ',b['content'])) for b in verifier.get('blocks',[])
        if b['label'] not in ['image','figure','chart','picture'])
    actual='\n'.join(line['text'] for line in record['lines'])
    return bool(normalized(actual)) and content_error(text,actual)==0


def clear_shapes(slide):
    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)


def content_error(reference,text):
    a,b=Counter(normalized(reference)),Counter(normalized(text))
    chars=sum((a-b).values())+sum((b-a).values())
    a,b=numeric_tokens(reference),numeric_tokens(text)
    numbers=sum((a-b).values())+sum((b-a).values())
    return chars+numbers*10


def coherent_ink(mask):
    """Ignore isolated scan specks for font bounds, without changing OCR text."""
    padded=np.pad(mask.astype(np.uint8),1)
    neighbors=sum(padded[y:y+mask.shape[0],x:x+mask.shape[1]] for y in range(3) for x in range(3))
    return mask & (neighbors>=3)


def ocr_slide(prs,slide,page,image_path,record,verified=None,line_approvals=None):
    validate_ocr(record,image_path)
    with Image.open(image_path) as im:image=im.convert('RGB').copy()
    a=np.array(image);accepted=[];warnings=[]
    if line_approvals is not None and (len(line_approvals)!=len(record['lines']) or any(type(x)!=bool for x in line_approvals)):
        raise ConversionError('invalid_ocr_consensus')
    overlaps=overlapping_lines(record['lines'])
    for index,line in enumerate(record['lines']):
        if (line_approvals is not None and not line_approvals[index]) or (line_approvals is None and verified is False):
            warnings.append('ocr_models_disagree_kept_as_image');continue
        if index in overlaps:
            warnings.append('overlapping_ocr_kept_as_image');continue
        box=np.array(line['polygon']);l,t,r,b=erase_bounds(line)
        l=max(0,l);t=max(0,t);r=min(image.width,r);b=min(image.height,b)
        if r-l<2 or b-t<2:continue
        if line['confidence']<.9:
            warnings.append('low_confidence_text_kept_as_image');continue
        # Uniform light backgrounds, including tinted paper. Compare each RGB channel
        # to its median; a uniformly colored border is not inherently nonuniform.
        crop=a[t:b,l:r];border=np.concatenate((crop[0],crop[-1],crop[:,0],crop[:,-1]))
        background=np.median(border,axis=0)
        if background.min()<180 or np.quantile(np.abs(border.astype(float)-background),.95)>12:
            warnings.append('nonuniform_background_kept_as_image');continue
        if abs(box[0,1]-box[1,1])>max(3,(b-t)*.12):
            warnings.append('rotated_ocr_kept_as_image');continue
        ink_mask=np.max(background-crop.astype(float),axis=2)>65
        ink=np.argwhere(coherent_ink(ink_mask))
        if not len(ink):
            warnings.append('no_visible_ink_kept_as_image');continue
        bounds=(l,t,r,b)
        if len(ink):bounds=(l+int(ink[:,1].min()),t+int(ink[:,0].min()),l+int(ink[:,1].max())+1,t+int(ink[:,0].max())+1)
        color=tuple(int(x) for x in np.quantile(crop[ink_mask],.2,axis=0))
        a[t:b,l:r]=background.astype(np.uint8)
        accepted.append((line,*bounds,color,background))
    w,h=page.get_size();sw,sh=prs.slide_width/12700,prs.slide_height/12700
    scale=min(sw/w,sh/h);ox=(sw-w*scale)/2;oy=(sh-h*scale)/2
    clear_shapes(slide);add_background(slide,Image.fromarray(a),w*scale,h*scale,(ox,oy))
    font_choices=[]
    for line,l,t,r,b,color,background in accepted:
        sx=w*scale/image.width;sy=h*scale/image.height;size=(b-t)*sy/0.75
        family,_=font_family('Arial',line['text'])
        # Glyph height alone is not evidence of bold (especially mixed CJK/Latin).
        bold=False
        choice=latin_font(line['text'],image.crop((l,t,r,b)),background,os.getenv('SMARTPPT_FONT_DIR','/System/Library/Fonts/Supplemental'))
        if choice:
            family=choice['family'];bold=choice['bold']
            font_choices.append(family+(' Bold' if bold else ''))
            if not choice['matched']:warnings.append('font_identity_unverified')
        metric_path=Path(os.getenv('SMARTPPT_FONT_DIR','/System/Library/Fonts/Supplemental'))/('Arial Bold.ttf' if bold else 'Arial.ttf')
        if choice:metric_path=Path(choice['path'])
        if family=='Noto Sans SC':metric_path=Path(os.getenv('SMARTPPT_CJK_FONT','NotoSansSC-variable.ttf'))
        if metric_path.exists():
            font=ImageFont.truetype(str(metric_path),100)
            size=min(size,(r-l)*sx/max(1,font.getlength(line['text']))*100)
        else:warnings.append('font_metrics_unavailable')
        add_text(slide,line['text'],ox+l*sx,oy+t*sy-size*.18,(r-l)*sx+size*.3,size*1.5,size,family,bold,color)
    if not record['lines']:warnings.append('no_ocr_text_detected')
    if len(accepted)<len(record['lines']):warnings.append('partial_ocr_editability')
    return {'route':'paddle-ocr','detected_lines':len(record['lines']),'editable_lines':len(accepted),
        'independent_model_agreement':verified,
        'region_verified_lines':sum(line_approvals) if line_approvals is not None else None,
        'estimated_fonts':sorted(set(font_choices)),
        'warnings':sorted(set(warnings+['ocr_requires_review'])),'graphics':'raster; not editable'}


def assist(source,target,settings,cached_ocr=None,cached_verifiers=None,cached_oxr=None):
    prs=Presentation(target);report=[]
    with tempfile.TemporaryDirectory(prefix='smartppt-ocr-',dir=Path(source).parent) as folder,pdfium.PdfDocument(source) as doc:
        if len(prs.slides)!=len(doc):raise ConversionError('page_count_mismatch')
        folder=Path(folder);scan_images={}
        for i in range(len(doc)):
            with closing(doc[i]) as page:
                if scan_page(page):
                    path=folder/f'page-{i+1}.png';render_page(source,i,max_side=1900).save(path);scan_images[i]=path
        records={};verifiers={};oxr_records={}
        if scan_images:
            if cached_ocr is not None:records=cached_ocr
            else:
                python=Path(settings.ocr_python);runner=Path(settings.ocr_runner)
                if not python.is_file() or not runner.is_file():raise ConversionError('ocr_not_configured')
                try:
                    subprocess.run([str(python),str(runner),'--out',str(folder),*[str(p) for p in scan_images.values()]],
                        check=True,timeout=settings.job_timeout,capture_output=True,
                        env=dict(os.environ,HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1'))
                except subprocess.TimeoutExpired as error:raise ConversionError('ocr_timeout') from error
                except subprocess.CalledProcessError as error:raise ConversionError('ocr_failed') from error
                records={i:json.loads((folder/(p.stem+'.json')).read_text()) for i,p in scan_images.items()}
            if cached_verifiers is not None:verifiers=cached_verifiers
            elif settings.ocr_verifier_python or settings.ocr_verifier_runner:
                python=Path(settings.ocr_verifier_python);runner=Path(settings.ocr_verifier_runner)
                if not python.is_file() or not runner.is_file():raise ConversionError('ocr_verifier_not_configured')
                dest=folder/'verification';dest.mkdir()
                try:
                    subprocess.run([str(python),str(runner),'--out',str(dest),*[str(p) for p in scan_images.values()]],
                        check=True,timeout=settings.job_timeout,capture_output=True,
                        env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1'))
                except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as error:
                    raise ConversionError('ocr_verifier_failed') from error
                verifiers={i:json.loads((dest/(p.stem+'.json')).read_text()) for i,p in scan_images.items()}
            if cached_oxr is not None:oxr_records=cached_oxr
            elif settings.oxr_python or settings.oxr_runner:
                python=Path(settings.oxr_python);runner=Path(settings.oxr_runner)
                if not python.is_file() or not runner.is_file():raise ConversionError('oxr_not_configured')
                dest=folder/'oxr';dest.mkdir()
                try:
                    subprocess.run([str(python),str(runner),'--out',str(dest),*[str(p) for p in scan_images.values()]],
                        check=True,timeout=settings.job_timeout,capture_output=True,
                        env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1'))
                except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as error:
                    raise ConversionError('oxr_failed') from error
                oxr_records={i:json.loads((dest/(p.stem+'.json')).read_text()) for i,p in scan_images.items()}
        for i,slide in enumerate(prs.slides):
            with closing(doc[i]) as page:
                if i in scan_images:
                    if i not in records:raise ConversionError('ocr_result_missing')
                    verified=verify_agreement(records[i],verifiers[i],scan_images[i]) if i in verifiers else None
                    approvals=region_agreement(records[i],verifiers[i]) if i in verifiers else None
                    if i in oxr_records:
                        oxr=region_agreement(records[i],oxr_records[i])
                        approvals=[a and b for a,b in zip(approvals,oxr)] if approvals is not None else oxr
                    if approvals is None:
                        # A single recognizer's confidence is not independent evidence.
                        approvals=[False]*len(records[i]['lines'])
                    item=ocr_slide(prs,slide,page,scan_images[i],records[i],verified,approvals)
                    if i not in verifiers and i not in oxr_records:
                        item['warnings'].append('independent_ocr_verification_unavailable')
                    item['verification_engines']=(['Unlimited OCR 2'] if i in verifiers else [])+(['SoMark OXR'] if i in oxr_records else [])
                else:
                    with closing(page.get_textpage()) as tp:reference=tp.get_text_range()
                    if safe_table(slide,reference):item={'route':'stirling-table','warnings':['table_layout_requires_review']}
                    else:
                        original=[deepcopy(s._element) for s in slide.shapes]
                        before='\n'.join(shape_text(slide.shapes))
                        clear_shapes(slide);item=native_slide(prs,page,slide)
                        after='\n'.join(shape_text(slide.shapes))
                        if content_error(reference,after)>content_error(reference,before):
                            clear_shapes(slide)
                            for element in original:slide.shapes._spTree.insert_element_before(element,'p:extLst')
                            item={'route':'stirling-retained','warnings':['coordinate_repair_rejected_for_content_loss']}
                report.append({'page':i+1,**item})
        prs.save(target)
    return {'pages':report,'verdict':'needs_review','fully_editable':False}
