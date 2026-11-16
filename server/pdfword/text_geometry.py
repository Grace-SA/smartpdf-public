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


def repair_zero_width_blocks(page, blocks):
    """Recover one visible glyph's actual ink box after native visibility checks.

    Never invent an advance width or remove the text. Ambiguous mappings are left
    unchanged so the caller can route the page through OCR.
    """
    from contextlib import closing
    if page.get_rotation():
        return
    targets = [b for b in blocks
               if b["kind"] in {"paragraph", "list", "title", "header", "footer"}
               and len(b.get("text", "").strip()) == 1
               and b["bbox"][0] == b["bbox"][2]
               and b["bbox"][1] < b["bbox"][3]]
    if not targets:
        return
    left, _, _, top = page.get_bbox()
    with closing(page.get_textpage()) as textpage:
        count = textpage.count_chars()
        if count > 100000 or count * len(targets) > 1000000:
            return
        wanted = {ord(b["text"].strip()) for b in targets}
        glyphs = []
        for index in range(count):
            code = pdf.raw.FPDFText_GetUnicode(textpage, index)
            if code not in wanted:
                continue
            x0, y0, x1, y1 = textpage.get_charbox(index)
            bounds = [x0-left, top-y1, x1-left, top-y0]
            if all(math.isfinite(v) for v in bounds) and bounds[0] < bounds[2] and bounds[1] < bounds[3]:
                glyphs.append((code, bounds))
        for block in targets:
            x, y0, _, y1 = block["bbox"]
            matches = [bounds for code, bounds in glyphs
                       if code == ord(block["text"].strip())
                       and abs(bounds[0]-x) <= 2
                       and bounds[1] >= y0-1 and bounds[3] <= y1+1]
            if len(matches) == 1:
                block["bbox"] = matches[0]


def repair_unmapped_glyphs(page, native):
    """Recover unmapped native glyphs only from unique independent Unicode/ink boxes.

    This returns a separate pdfplumber view. Ambiguous, rotated or cropped pages
    remain untouched, so native extraction's CID guard can require OCR.
    """
    import re
    import unicodedata
    from contextlib import closing

    if len(native.chars) > 60000:
        return native
    targets = [(i, c) for i, c in enumerate(native.chars)
               if re.fullmatch(r"\(cid:\d+\)", c.get("text", ""))]
    if not targets or page.get_rotation() or native.rotation:
        return native
    width, height = page.get_size()
    expected = (0, 0, width, height)
    if any(abs(a-b) > .01 for bounds in (page.get_bbox(), native.bbox)
           for a, b in zip(bounds, expected)):
        return native
    if len(targets) > 256:
        return native
    with closing(page.get_textpage()) as textpage:
        count = textpage.count_chars()
        if count > 100000 or count * len(targets) > 1000000:
            return native
        glyphs = []
        for index in range(count):
            code = pdf.raw.FPDFText_GetUnicode(textpage, index)
            char = chr(code) if 0 < code <= 0x10ffff else None
            if char and char.isspace():
                continue
            l, b, r, t = textpage.get_charbox(index)
            bounds = (l, height-t, r, height-b)
            if (all(math.isfinite(v) for v in bounds)
                    and bounds[0] < bounds[2] and bounds[1] < bounds[3]):
                glyphs.append((index, char, bounds))
    replacements, used = {}, set()
    for index, target in targets:
        bounds = [target[k] for k in ("x0", "top", "x1", "bottom")]
        if (not all(math.isfinite(v) for v in bounds)
                or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]):
            return native
        matches = [(i, char) for i, char, b in glyphs
                   if b[0] >= bounds[0]-.5 and b[1] >= bounds[1]-.5
                   and b[2] <= bounds[2]+.5 and b[3] <= bounds[3]+.5]
        if len(matches) != 1:
            return native
        glyph, char = matches[0]
        if glyph in used or char is None or char == "\ufffd" or unicodedata.category(char)[0] in "CM":
            return native
        used.add(glyph)
        replacements[index] = char
    repaired = native.filter(lambda _: True)
    # pdfplumber's own dedupe_chars uses this same independent object-cache view.
    repaired._objects = dict(native.objects)
    repaired._objects["char"] = [dict(c, text=replacements[i]) if i in replacements else c
                                  for i, c in enumerate(native.chars)]
    return repaired
