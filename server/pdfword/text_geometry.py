"""Use mapped glyph ink bounds when PDF object bounds include unused advances."""
import collections
import ctypes
import math

import pypdfium2 as pdf


def handle(obj):
    return ctypes.cast(getattr(obj, "raw", obj), ctypes.c_void_p).value


def glyph_geometry(textpage):
    # An absent or incomplete mapping must retain the conservative object bounds.
    if textpage.count_chars() > 100000:
        return {}
    groups = {}
    for index in range(textpage.count_chars()):
        code = pdf.raw.FPDFText_GetUnicode(textpage, index)
        if not code or code > 0x10ffff or chr(code).isspace():
            continue
        owner = handle(pdf.raw.FPDFText_GetTextObject(textpage, index))
        if owner is None:
            continue
        bounds = textpage.get_charbox(index)
        if not all(math.isfinite(x) for x in bounds):
            continue
        group = groups.setdefault(owner, {"characters": collections.Counter(), "boxes": []})
        group["characters"][chr(code)] += 1
        group["boxes"].append(bounds)
    return groups


def mapped_bounds(obj, geometry):
    group = geometry.get(handle(obj))
    expected = collections.Counter(c for c in obj.extract() if not c.isspace())
    if not group or not expected or group["characters"] != expected:
        return None
    boxes = group["boxes"]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def ink_bounds(obj, geometry):
    return mapped_bounds(obj, geometry) or obj.get_bounds()
