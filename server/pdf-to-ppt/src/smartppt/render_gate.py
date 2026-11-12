"""Independent render gate: coordinate repair must not worsen measured layout."""
from copy import deepcopy
from contextlib import closing
import os,subprocess,tempfile
from pathlib import Path
from xml.sax.saxutils import escape
import numpy as np
from PIL import Image,ImageOps
from pptx import Presentation
from .config import ConversionError
from .pdf import render_page


def metric(source,output,index):
    a=render_page(source,index,max_side=900);b=render_page(output,index,max_side=900)
    expected=Image.new('RGB',b.size,'white');im=ImageOps.contain(a,b.size,Image.Resampling.LANCZOS)
    expected.paste(im,((b.width-im.width)//2,(b.height-im.height)//2))
    av,bv=np.asarray(expected,dtype=float),np.asarray(b,dtype=float)
    mask=(av.min(axis=2)<245)|(bv.min(axis=2)<245)
    return {'mae':float(np.abs(av-bv).mean()/255),
        'foreground_mae':float(np.abs(av-bv)[mask].mean()/255) if mask.any() else 0}


def accept_candidate(before,after):
    return after['mae']<=before['mae']+.001 and after['foreground_mae']<=before['foreground_mae']+.01


def compare_and_restore(original,target,source,report,baseline_pdf,candidate_pdf):
    baseline=Presentation(original);candidate=Presentation(target)
    if len(baseline.slides)!=len(candidate.slides):raise ConversionError('page_count_mismatch')
    for i,item in enumerate(report['pages']):
        if item['route']!='native-coordinate':continue
        before=metric(source,baseline_pdf,i);after=metric(source,candidate_pdf,i)
        item['render_gate']={'baseline':before,'candidate':after,'accepted':accept_candidate(before,after)}
        if not item['render_gate']['accepted']:
            slide=candidate.slides[i];old=baseline.slides[i]
            # Candidate starts from the original package and retains original relationships.
            for shape in old.shapes:
                for node in shape._element.iter():
                    for attr,value in node.attrib.items():
                        if attr.startswith('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}') and value not in slide.part.rels:
                            raise ConversionError('cannot_restore_slide_relationship')
            for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
            for shape in old.shapes:slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
            item['route']='stirling-retained-visual'
            item.setdefault('warnings',[]).append('coordinate_repair_rejected_for_visual_regression')
    candidate.save(target)
    return report


def render_presentations(files, folder, settings):
    """Render in a job-owned directory; callers validate the resulting pages."""
    if not settings.renderer_path or not Path(settings.renderer_path).is_file():
        raise ConversionError('layout_renderer_not_configured')
    folder=Path(folder);config=folder/'fonts.conf'
    font_dirs=[Path('/System/Library/Fonts'),Path('/usr/share/fonts')]
    if os.getenv('SMARTPPT_FONT_DIR'):font_dirs.append(Path(os.environ['SMARTPPT_FONT_DIR']))
    if os.getenv('SMARTPPT_CJK_FONT'):font_dirs.append(Path(os.environ['SMARTPPT_CJK_FONT']).parent)
    dirs=''.join('<dir>'+escape(str(p))+'</dir>' for p in font_dirs if p.exists())
    config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'+dirs+
        '<cachedir>'+escape(str(folder/'cache'))+'</cachedir><alias><family>SimSun</family><prefer><family>Noto Sans SC</family></prefer></alias></fontconfig>')
    env=dict(os.environ,FONTCONFIG_FILE=str(config),XDG_CACHE_HOME=str(folder/'cache'),TMPDIR=str(folder))
    try:
        subprocess.run([settings.renderer_path,'-env:UserInstallation='+(folder/'profile').as_uri(),
            '--headless','--convert-to','pdf','--outdir',str(folder),*[str(p) for p in files]],
            capture_output=True,check=True,timeout=min(settings.job_timeout,180),env=env)
    except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as error:
        raise ConversionError('layout_render_failed') from error
    outputs=[folder/(Path(p).stem+'.pdf') for p in files]
    if not all(p.is_file() for p in outputs):raise ConversionError('layout_render_failed')
    return outputs


def run_gate(original,target,source,report,settings):
    if any(p['route']=='native-coordinate' for p in report['pages']):
        if not settings.renderer_path or not Path(settings.renderer_path).is_file():raise ConversionError('layout_renderer_not_configured')
        with tempfile.TemporaryDirectory(prefix='smartppt-render-gate-',dir=Path(source).parent) as folder:
            import shutil
            folder=Path(folder)
            a=folder/'baseline.pptx';b=folder/'candidate.pptx';shutil.copyfile(original,a);shutil.copyfile(target,b)
            ap,bp=render_presentations([a,b],folder,settings)
            compare_and_restore(original,target,source,report,ap,bp)
    from .native_words import try_native_words
    return try_native_words(source,target,report,settings)
