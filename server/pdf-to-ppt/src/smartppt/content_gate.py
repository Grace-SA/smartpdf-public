"""Preserve source appearance when a native-text conversion has known content loss.

This is an explicit loss of editability, not a successful text reconstruction.
Retain pre-fallback diagnostics so corpus evaluation cannot hide failed recovery.
"""
from pptx import Presentation
from .assisted import clear_shapes
from .layout import add_background
from .pdf import render_page
from .quality import inspect_pptx


def enforce_content_safety(source, target, info, assistance):
    before = inspect_pptx(target, info, 'editable')
    severe = {'text_mismatch', 'numeric_mismatch', 'replacement_character'}
    problems = {}
    for warning in before['warnings']:
        if warning['code'] in severe:
            problems.setdefault(warning['page'], []).append(warning['code'])
    prs = Presentation(target); changed = False
    for item in assistance['pages']:
        page = item['page']; codes = problems.get(page, [])
        # A scan has no trusted PDF text layer; hidden OCR must not be used as truth.
        if item['route'] == 'paddle-ocr' or not codes:
            continue
        slide = prs.slides[page-1]
        image = render_page(source, page-1, max_side=2200)
        sw, sh = prs.slide_width/12700, prs.slide_height/12700
        scale = min(sw/image.width, sh/image.height)
        w, h = image.width*scale, image.height*scale
        clear_shapes(slide); add_background(slide, image, w, h, ((sw-w)/2, (sh-h)/2))
        previous = dict(item)
        item.clear()
        item.update(page=page, route='source-image-fallback', editable_runs=0,
                    warnings=['content_recovery_failed_page_kept_as_image'],
                    content_gate={'triggered_by': codes, 'before': before['pages'][page-1],
                                  'attempt': previous})
        changed = True
    if changed:
        prs.save(target)
    assistance['source_image_pages'] = [p['page'] for p in assistance['pages'] if p['route']=='source-image-fallback']
    assistance['content_gate'] = 'fallback is appearance-only; original recovery failures retained'
    return assistance
