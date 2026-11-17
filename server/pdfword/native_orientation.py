"""Canonical native text direction, with exact render comparison before adoption."""
import math
import ctypes
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdf
from text_geometry import glyph_geometry
from native_margins import numeric_margin
from PIL import ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject


def normalize_orientation(source, work, cancel=None):
    from model import Rejected
    rotations = {}
    with pdf.PdfDocument(source) as document:
        for index in range(len(document)):
            if cancel and Path(cancel).exists():
                raise Rejected("Conversion cancelled.")
            with closing(document[index]) as page, closing(page.get_textpage()) as textpage:
                angles = set()
                geometry = glyph_geometry(textpage)
                count = 0
                for number, obj in enumerate(page.get_objects(max_depth=8, textpage=textpage)):
                    if number >= 10000:
                        angles.add(-1)
                        break
                    if obj.type == pdf.raw.FPDF_PAGEOBJ_IMAGE:
                        angles.add(-1)
                        break
                    if obj.type != pdf.raw.FPDF_PAGEOBJ_TEXT or not obj.extract().strip():
                        continue
                    if obj.level:
                        angles.add(-1)
                        break
                    rgba = [ctypes.c_uint() for _ in range(4)]
                    if (pdf.raw.FPDFTextObj_GetTextRenderMode(obj) != 0
                            or not pdf.raw.FPDFPageObj_GetFillColor(obj, *(ctypes.byref(v) for v in rgba))
                            or rgba[3].value != 255):
                        angles.add(-1)
                        break
                    if numeric_margin(obj, page, geometry):
                        continue
                    count += len(obj.extract().strip())
                    m = obj.get_matrix()
                    angle = math.degrees(math.atan2(m.b, m.a)) % 360
                    nearest = round(angle/90)*90 % 360
                    # Do not alter skewed, mirrored, mixed-direction or vertical-script pages.
                    if (min(abs(angle-nearest), abs(angle-nearest-360)) > .01
                            or m.a*m.d-m.b*m.c <= 0
                            or abs(m.a*m.c+m.b*m.d) > .001):
                        angles.add(-1)
                    else:
                        angles.add(nearest)
                if count >= 32 and len(angles) == 1:
                    angle = next(iter(angles))
                    if angle >= 0 and (angle or page.get_rotation()):
                        rotations[index] = (angle, page.get_rotation())
    if not rotations:
        return source, []
    reader = PdfReader(source)
    writer = PdfWriter()
    for index, original_page in enumerate(reader.pages):
        page = writer.add_page(original_page)
        if index in rotations:
            page[NameObject('/Rotate')] = NumberObject(rotations[index][0])
            page.transfer_rotation_to_content()
    candidate = Path(work) / 'native-upright.pdf'
    writer.write(candidate)
    with pdf.PdfDocument(source) as original, pdf.PdfDocument(candidate) as normalized:
        for index, (angle, original_angle) in rotations.items():
            if cancel and Path(cancel).exists():
                raise Rejected("Conversion cancelled.")
            with closing(original[index]) as before, closing(normalized[index]) as after:
                width, height = before.get_size()
                scale = min(2, math.sqrt(8000000/(width*height)))
                with closing(before.render(scale=scale, rotation=(angle-original_angle) % 360)) as a, closing(after.render(scale=scale)) as b:
                    with a.to_pil().convert('RGB') as left, b.to_pil().convert('RGB') as right:
                        if left.size != right.size:
                            return source, []
                        with ImageChops.difference(left, right) as difference:
                            if difference.getbbox() is not None:
                                return source, []
    return candidate, sorted(rotations)
