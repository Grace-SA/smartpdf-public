"""Explicit page mapping for partial temporary renders; no placeholder pages."""
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as ET
from pptx import Presentation
from .config import ConversionError
from .render_gate import render_presentations
from .pdf import render_page


@dataclass(frozen=True)
class SelectedRender:
    path: Path
    pages: tuple[int, ...]


def render_selected(files,folder,settings,page_numbers):
    pages=tuple(page_numbers)
    if (not pages or any(type(n) is not int or n<1 for n in pages)
            or tuple(sorted(set(pages)))!=pages):raise ConversionError('invalid_render_page_selection')
    files=list(files);presentations=[Presentation(path) for path in files]
    if any(pages[-1]>len(prs.slides) for prs in presentations):raise ConversionError('invalid_render_page_selection')
    # Actual slide fields/placeholders or custom sections can depend on other
    # slides. Unused template layouts commonly contain dormant page/date
    # fields; they do not make plain raster-plus-text slides contextual.
    contextual=False
    for path in files:
        with ZipFile(path) as package:
            for name in package.namelist():
                if not (name=='ppt/presentation.xml' or name.startswith('ppt/slides/slide') and name.endswith('.xml')):continue
                root=ET.fromstring(package.read(name),ET.XMLParser(resolve_entities=False,no_network=True))
                if any(isinstance(node.tag,str) and node.tag.rsplit('}',1)[-1] in ('fld','sectionLst','custShowLst','ph','hf') for node in root.iter()):contextual=True;break
        if contextual:break
    inputs=files;export_pages=pages
    if not contextual:
        directory=Path(folder)/'selected-inputs';directory.mkdir(exist_ok=True)
        inputs=[];wanted=set(pages)
        for path,prs in zip(files,presentations):
            for number,slide_id in reversed(list(enumerate(prs.slides._sldIdLst,1))):
                if number in wanted:continue
                prs.part.drop_rel(slide_id.rId);prs.slides._sldIdLst.remove(slide_id)
            selected=directory/Path(path).name
            if selected.resolve()==Path(path).resolve():raise ConversionError('layout_render_name_collision')
            prs.save(selected);inputs.append(selected)
        export_pages=tuple(range(1,len(pages)+1))
    outputs=render_presentations(inputs,folder,settings,page_numbers=export_pages)
    return [SelectedRender(p,pages) for p in outputs]


def location(rendered,number):
    if isinstance(rendered,SelectedRender):
        try:index=rendered.pages.index(number)
        except ValueError as error:raise ConversionError('unrendered_page_requested') from error
        return rendered.path,index
    return rendered,number-1


def page_image(rendered,number,**kwargs):
    path,index=location(rendered,number)
    return render_page(path,index,**kwargs)


def page_metric(source,rendered,number):
    from .render_gate import metric
    path,index=location(rendered,number)
    return metric(source,path,number-1,output_index=index)
