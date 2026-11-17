"""Explicit appearance-only mode. Never presented as editable conversion."""
from io import BytesIO
from pptx import Presentation
from pptx.util import Pt
from .pdf import render_page


def convert_preserve(source, target, info):
    prs = Presentation()
    first = info['pages'][0]
    # PowerPoint has one canvas size for the whole deck. Keep page aspect ratio.
    factor = min(1, 4000/max(first['width'], first['height']))
    # OOXML slide dimensions must be at least one inch. Tiny PDF artboards
    # receive margins instead of failing or distorting their content.
    sw, sh = max(72, first['width']*factor), max(72, first['height']*factor)
    prs.slide_width, prs.slide_height = Pt(sw), Pt(sh)
    for i, page in enumerate(info['pages']):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        image = render_page(source, i)
        buf = BytesIO(); image.save(buf, 'PNG'); buf.seek(0)
        scale = min(sw/page['width'], sh/page['height'])
        w, h = page['width']*scale, page['height']*scale
        slide.shapes.add_picture(buf, Pt((sw-w)/2), Pt((sh-h)/2), Pt(w), Pt(h))
        slide.notes_slide.notes_text_frame.text = 'Appearance-only conversion. Page content is an image and is not editable text.'
    prs.save(target)
