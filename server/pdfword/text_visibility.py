"""Check bright native glyphs against the rendered page, never trust text color alone."""
import math
from contextlib import closing
import pypdfium2 as pdf
from PIL import ImageChops
from text_geometry import ink_bounds, mapped_bounds, handle


def fully_clipped_number(obj, geometry):
    """Only fully mapped root-level numeric labels outside rectangular clips."""
    import ctypes
    import re
    if obj.level or not re.fullmatch(r"[0-9]{1,16}", obj.extract().strip()):
        return False
    if pdf.raw.FPDFTextObj_GetTextRenderMode(obj) not in (0, 1, 2):
        return False
    bounds = mapped_bounds(obj, geometry)
    if bounds is None:
        return False
    clip = pdf.raw.FPDFPageObj_GetClipPath(obj)
    paths = pdf.raw.FPDFClipPath_CountPaths(clip)
    if not 1 <= paths <= 64:
        return False
    outside = False
    for index in range(paths):
        count = pdf.raw.FPDFClipPath_CountPathSegments(clip, index)
        if count not in (4, 5):
            return False
        points = []
        for part in range(count):
            segment = pdf.raw.FPDFClipPath_GetPathSegment(clip, index, part)
            x, y = ctypes.c_float(), ctypes.c_float()
            if (pdf.raw.FPDFPathSegment_GetType(segment) not in (0, 2)
                    or not pdf.raw.FPDFPathSegment_GetPoint(segment, ctypes.byref(x), ctypes.byref(y))):
                return False
            points.append((round(x.value, 3), round(y.value, 3)))
        if any(not math.isfinite(v) for point in points for v in point):
            return False
        xs, ys = {p[0] for p in points}, {p[1] for p in points}
        if (len(xs) != 2 or len(ys) != 2 or len(set(points)) != 4
                or any(a[0] != b[0] and a[1] != b[1]
                       for a, b in zip(points, points[1:] + points[:1]))):
            return False
        l, b, r, t = bounds
        outside |= (r < min(xs) - .5 or l > max(xs) + .5
                    or t < min(ys) - .5 or b > max(ys) + .5)
    return outside


def confirm_invisible_numbers(page, objects):
    """Confirm geometric exclusion by RGB equality; never rewrite the source PDF."""
    if not objects or len(objects) > 32:
        return not objects
    width, height = page.get_size()
    scale = min(3, math.sqrt(8000000 / (width * height)))
    with closing(page.render(scale=scale)) as bitmap:
        before = bitmap.to_pil().convert("RGB")
    modes = [(obj, pdf.raw.FPDFTextObj_GetTextRenderMode(obj)) for obj in objects]
    try:
        try:
            for obj, _ in modes:
                if not pdf.raw.FPDFTextObj_SetTextRenderMode(obj, 3):
                    return False
            with closing(page.render(scale=scale)) as bitmap:
                after = bitmap.to_pil().convert("RGB")
            with after, ImageChops.difference(before, after) as difference:
                return difference.getbbox() is None
        finally:
            for obj, mode in modes:
                pdf.raw.FPDFTextObj_SetTextRenderMode(obj, mode)
    finally:
        before.close()


def text_without_objects(textpage, objects):
    excluded = {handle(obj) for obj in objects}
    result = []
    for index in range(textpage.count_chars()):
        if handle(pdf.raw.FPDFText_GetTextObject(textpage, index)) in excluded:
            continue
        code = pdf.raw.FPDFText_GetUnicode(textpage, index)
        if code:
            result.append(chr(code))
    return "".join(result)


def bright_text_visible(page, objects, geometry=None):
    if not objects:
        return True
    width, height = page.get_size()
    scale = min(1.5, math.sqrt(4000000 / (width * height)))
    with closing(page.render(scale=scale)) as bitmap:
        image = bitmap.to_pil().convert("L")
        coordinates = bitmap.get_posconv(page)
        modes = [(obj, pdf.raw.FPDFTextObj_GetTextRenderMode(obj)) for obj in objects]
        try:
            try:
                for obj, _ in modes:
                    if not pdf.raw.FPDFTextObj_SetTextRenderMode(obj, 3):
                        return False
                with closing(page.render(scale=scale)) as without:
                    hidden = without.to_pil().convert("L")
            finally:
                for obj, mode in modes:
                    pdf.raw.FPDFTextObj_SetTextRenderMode(obj, mode)
            difference = ImageChops.difference(image, hidden)
            hidden.close()
            for obj in objects:
                l, b, r, t = ink_bounds(obj, geometry) if geometry is not None else obj.get_bounds()
                points = [coordinates.to_bitmap(x, y) for x in (l, r) for y in (b, t)]
                xs, ys = zip(*points)
                crop = (max(0, min(xs)-1), max(0, min(ys)-1),
                        min(image.width, max(xs)+2), min(image.height, max(ys)+2))
                if crop[2] <= crop[0] or crop[3] <= crop[1]:
                    return False
                region = difference.crop(crop)
                counts = region.histogram()
                pixels = region.width * region.height
                region.close()
                # Detect an actual contribution from the glyphs, not just unrelated
                # dark/bright pixels behind an invisible or occluded text object.
                if sum(counts[16:]) < max(2, pixels * 0.01):
                    return False
            return True
        finally:
            image.close()
            if "difference" in locals():
                difference.close()


def cosmetic_white_rectangles(page):
    """Prove that opaque white root rectangles contribute no rendered pixels.

    White paint alone is not evidence: it may cover earlier text or graphics.
    Disable all candidates together, compare RGB pixels, and always restore the
    original drawing modes. Ambiguous transforms/forms and large object sets
    retain the ordinary graphics/OCR route.
    """
    import ctypes
    from itertools import islice
    width, height = page.get_size()
    if page.get_rotation() or any(abs(a-b) > .01 for a, b in
            zip(page.get_bbox(), (0, 0, width, height))):
        return []
    candidates = []
    prior_bounds = []
    for number, obj in enumerate(page.get_objects(max_depth=1)):
        if number >= 10000:
            return []
        bounds = obj.get_bounds()
        prior_count = len(prior_bounds)
        prior_bounds.append(bounds)
        if obj.type != pdf.raw.FPDF_PAGEOBJ_PATH:
            continue
        matrix = obj.get_matrix()
        if matrix.get() != (1, 0, 0, 1, 0, 0):
            continue
        rgba = [ctypes.c_uint() for _ in range(4)]
        fill, stroke = ctypes.c_int(), ctypes.c_int()
        if not (pdf.raw.FPDFPageObj_GetFillColor(obj, *(ctypes.byref(v) for v in rgba))
                and [v.value for v in rgba] == [255]*4
                and pdf.raw.FPDFPath_GetDrawMode(obj, ctypes.byref(fill), ctypes.byref(stroke))
                and fill.value and not stroke.value):
            continue
        # Pixel equality alone cannot prove safety for subpixel hidden glyphs.
        # A removable background must also precede every overlapping non-cosmetic object.
        l, b, r, t = bounds
        if any(min(r, right) > max(l, left) and min(t, top) > max(b, bottom)
               for left, bottom, right, top in islice(prior_bounds, prior_count)):
            continue
        count = pdf.raw.FPDFPath_CountSegments(obj)
        if count not in (4, 5):
            continue
        points = []
        for index in range(count):
            segment = pdf.raw.FPDFPath_GetPathSegment(obj, index)
            x, y = ctypes.c_float(), ctypes.c_float()
            if (pdf.raw.FPDFPathSegment_GetType(segment) not in (0, 2)
                    or not pdf.raw.FPDFPathSegment_GetPoint(segment, ctypes.byref(x), ctypes.byref(y))):
                break
            points.append((round(x.value, 3), round(y.value, 3)))
        if (len(points) != count or len(set(points)) != 4
                or len({p[0] for p in points}) != 2 or len({p[1] for p in points}) != 2
                or any(a[0] != b[0] and a[1] != b[1] for a, b in zip(points, points[1:]+points[:1]))):
            continue
        candidates.append((obj, fill.value, stroke.value))
        # Adjacent white backgrounds may overlap by PDF rounding. Earlier text
        # and graphics remain in prior_bounds, so overlapping them still fails.
        prior_bounds[-1] = (0, 0, 0, 0)
        if len(candidates) > 1024:
            return []
    if not candidates:
        return []
    scale = min(3, math.sqrt(8000000 / (width * height)))
    with closing(page.render(scale=scale)) as bitmap:
        before = bitmap.to_pil().convert("RGB")
    try:
        try:
            for obj, _, _ in candidates:
                if not pdf.raw.FPDFPath_SetDrawMode(obj, 0, 0):
                    return []
            with closing(page.render(scale=scale)) as bitmap:
                after = bitmap.to_pil().convert("RGB")
        finally:
            restored = all([bool(pdf.raw.FPDFPath_SetDrawMode(obj, fill, stroke))
                            for obj, fill, stroke in candidates])
            if not restored:
                raise ValueError("Could not restore PDF graphics for safe extraction.")
        with closing(after), closing(ImageChops.difference(before, after)) as difference:
            if difference.getbbox() is not None:
                return []
        return [(l, height-t, r, height-b)
                for obj, _, _ in candidates for l, b, r, t in [obj.get_bounds()]]
    finally:
        before.close()
