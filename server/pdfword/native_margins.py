"""Verified orthogonal numeric page labels remain editable after page rotation."""
import math
import re
import unicodedata
from contextlib import closing
import pypdfium2 as pdf
from text_geometry import mapped_bounds, glyph_geometry, handle


def numeric_margin(obj, page, geometry):
    if obj.level or not re.fullmatch(r'[0-9]{1,4}', obj.extract().strip()):
        return False
    bounds = mapped_bounds(obj, geometry)
    if bounds is None:
        return False
    m = obj.get_matrix()
    angle = math.degrees(math.atan2(m.b, m.a)) % 360
    nearest = round(angle/90)*90 % 360
    if (min(abs(angle-nearest), abs(angle-nearest-360)) > .01
            or m.a*m.d-m.b*m.c <= 0 or abs(m.a*m.c+m.b*m.d) > .001):
        return False
    l, b, r, t = page.get_bbox()
    x0, y0, x1, y1 = bounds
    return (l <= x0 < x1 <= r and b <= y0 < y1 <= t
            and (x1 <= l+(r-l)*.08 or x0 >= r-(r-l)*.08
                 or y1 <= b+(t-b)*.08 or y0 >= t-(t-b)*.08))


def upright_margin_words(page, native):
    """Combine only exactly mapped rotated digit labels; ambiguity requires OCR."""
    replacements = {}
    removed = set()
    with closing(page.get_textpage()) as textpage:
        geometry = glyph_geometry(textpage)
        for obj in page.get_objects(textpage=textpage):
            if obj.type != pdf.raw.FPDF_PAGEOBJ_TEXT or not numeric_margin(obj, page, geometry):
                continue
            m = obj.get_matrix()
            if abs(m.b) < .001 and abs(m.c) < .001 and m.a > 0 and m.d > 0:
                continue
            indices = []
            l, b, r, t = mapped_bounds(obj, geometry)
            top, bottom = native.height-t, native.height-b
            controls = [i for i, c in enumerate(native.chars)
                        if len(c['text']) == 1 and unicodedata.category(c['text']) == 'Cc'
                        and min(c['x1'], r) > max(c['x0'], l)
                        and min(c['bottom'], bottom) > max(c['top'], top)]
            if controls:
                chars = [native.chars[i] for i in controls]
                if (len(controls) != len(obj.extract().strip()) or removed.intersection(controls)
                        or min(c['x0'] for c in chars) > l+.5 or max(c['x1'] for c in chars) < r-.5
                        or min(c['top'] for c in chars) > top+.5 or max(c['bottom'] for c in chars) < bottom-.5
                        or max(c['x1'] for c in chars)-min(c['x0'] for c in chars) > (r-l)*2
                        or max(c['bottom'] for c in chars)-min(c['top'] for c in chars) > (bottom-top)*2):
                    return None
                indices = controls
                removed.update(controls)
            for index in range(textpage.count_chars()):
                if controls:
                    break
                if handle(pdf.raw.FPDFText_GetTextObject(textpage, index)) != handle(obj):
                    continue
                code = pdf.raw.FPDFText_GetUnicode(textpage, index)
                if not code or chr(code).isspace():
                    continue
                l, b, r, t = textpage.get_charbox(index)
                matches = [i for i, c in enumerate(native.chars)
                           if c['text'] == chr(code) and c['x0']-.5 <= l <= r <= c['x1']+.5
                           and c['top']-.5 <= native.height-t <= native.height-b <= c['bottom']+.5]
                if len(matches) != 1 or matches[0] in removed:
                    return None
                removed.add(matches[0])
                indices.append(matches[0])
            if len(indices) != len(obj.extract().strip()):
                return None
            l, b, r, t = mapped_bounds(obj, geometry)
            replacements[indices[0]] = dict(native.chars[indices[0]], text=obj.extract().strip(),
                                            x0=l, x1=r, top=native.height-t, bottom=native.height-b,
                                            width=r-l, height=t-b, size=t-b, upright=True)
    if not removed:
        return native
    view = native.filter(lambda _: True)
    view._objects = dict(native.objects)
    view._objects['char'] = [replacements[i] if i in replacements else c
                             for i, c in enumerate(native.chars) if i not in removed or i in replacements]
    return view
