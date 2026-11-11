"""Conservative text-PDF importer. Run each task in a disposable offline process.

The intermediate model deliberately separates PDF interpretation from Word export.
Rejected documents never produce a partial Word file. OCR is not enabled here.
"""
import argparse
import json
import math
import os
import tempfile
import ctypes
import unicodedata
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdf
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.shared import Pt
from pypdf import PdfReader


class Rejected(ValueError):
    pass


def text_geometry(textpage):
    """Validate glyph advances, including positioning hidden inside a TJ object.

    Object bounds alone cannot distinguish one sentence from two table cells.
    Generated separators are not glyphs and must not conceal abnormal advances.
    """
    count = textpage.count_chars()
    if count > 1000000:
        raise Rejected('The PDF contains too much text to convert.')
    groups = {}
    seams = {}
    previous_identifier = None
    separator = ''
    for index in range(count):
        if pdf.raw.FPDFText_HasUnicodeMapError(textpage, index):
            raise Rejected('The PDF text could not be read reliably.')
        code = pdf.raw.FPDFText_GetUnicode(textpage, index)
        if not code or code > 0x10ffff:
            raise Rejected('The PDF text could not be read reliably.')
        character = chr(code)
        if character.isspace():
            separator += character
            continue
        if pdf.raw.FPDFText_IsGenerated(textpage, index):
            raise Rejected('The PDF text structure needs review.')
        identifier = ctypes.cast(pdf.raw.FPDFText_GetTextObject(textpage, index), ctypes.c_void_p).value
        if identifier is None:
            raise Rejected('The PDF text structure needs review.')
        if previous_identifier is not None and previous_identifier != identifier:
            seams[(previous_identifier, identifier)] = separator
        previous_identifier, separator = identifier, ''
        bounds = textpage.get_charbox(index, loose=True)
        x, y = ctypes.c_double(), ctypes.c_double()
        if not pdf.raw.FPDFText_GetCharOrigin(textpage, index, ctypes.byref(x), ctypes.byref(y)):
            raise Rejected('The PDF text position needs review.')
        if not all(math.isfinite(v) for v in (*bounds, x.value, y.value)):
            raise Rejected('The PDF text position needs review.')
        glyph = (x.value, y.value, bounds, unicodedata.category(character))
        group = groups.setdefault(identifier, [])
        if group:
            previous = group[-1]
            em = max(bounds[3] - bounds[1], previous[2][3] - previous[2][1])
            if (abs(y.value - previous[1]) > 1
                    or x.value - previous[2][2] > max(6, em)
                    or (glyph[3] not in ('Mn', 'Mc', 'Me') and previous[3] not in ('Mn', 'Mc', 'Me')
                        and x.value < previous[0] + max(.05, (previous[2][2] - previous[2][0]) * .35))):
                raise Rejected('Tables, columns and overlapping text are not supported yet.')
        group.append(glyph)
    return groups, seams


def readable_lines(runs, seams):
    """Join adjacent horizontal runs without mistaking wide gaps for prose."""
    runs.sort(key=lambda item: -item[5])
    rows = []
    for run in runs:
        if rows and abs(rows[-1][0][5] - run[5]) <= 1:
            rows[-1].append(run)
        else:
            rows.append([run])
    lines = []
    for row in rows:
        row.sort(key=lambda item: item[2])
        combined = row[0]
        for run in row[1:]:
            previous = combined
            gap = run[6] - previous[7]
            if gap < -1 or gap > max(3, min(previous[8], run[8]) * .5):
                raise Rejected('Tables, columns and overlapping text are not supported yet.')
            if previous[4][-1:].isspace() or run[4][:1].isspace():
                separator = ''
            elif (previous[9], run[9]) in seams:
                separator = seams[(previous[9], run[9])]
                if any(c in '\r\n\t' for c in separator):
                    raise Rejected('The PDF text spacing needs review.')
            elif gap <= 1:
                separator = ''
            else:
                raise Rejected('The PDF text spacing needs review.')
            combined = (max(previous[0], run[0]), min(previous[1], run[1]),
                         min(previous[2], run[2]), max(previous[3], run[3]),
                         previous[4] + separator + run[4], previous[5],
                         previous[6], run[7], min(previous[8], run[8]), run[9])
        lines.append(combined)
    if any(a[1] < b[0] - 2 for a, b in zip(lines, lines[1:])):
        raise Rejected('Tables, columns and overlapping text are not supported yet.')
    # Disjoint horizontal text lanes with interleaved rows are not ordinary
    # wrapping. Refuse rather than silently alternate a staggered two-column PDF.
    for a, b, c in zip(lines, lines[1:], lines[2:]):
        if ((a[3] + 24 < b[2] and c[3] + 24 < b[2])
                or (b[3] + 24 < a[2] and b[3] + 24 < c[2])):
            raise Rejected('Tables, columns and overlapping text are not supported yet.')
    return lines


def parse_pdf(source):
    if not 0 < source.stat().st_size <= 30 * 1024**2:
        raise Rejected('Choose a PDF under 30 MB.')
    with source.open('rb') as stream:
        reader = PdfReader(stream, strict=True)
        if reader.is_encrypted:
            raise Rejected('Unlock the PDF before converting it.')
        count = len(reader.pages)
        if not 0 < count <= 200:
            raise Rejected('Choose a PDF with 1 to 200 pages.')
        root = reader.trailer['/Root']
        if any(key in root for key in ('/AcroForm', '/OCProperties', '/OpenAction', '/AA', '/Names')):
            raise Rejected('This PDF has interactive content. Export a simple PDF first.')
        for page in reader.pages:
            if page.get('/Annots') or page.get('/AA'):
                raise Rejected('This PDF has annotations or interactive content. Export a simple PDF first.')
    result = {'schema': 1, 'pages': [], 'issues': []}
    total = 0
    with pdf.PdfDocument(source) as original:
        if len(original) != count:
            raise Rejected('The PDF page structure needs review.')
        for index in range(count):
            with closing(original[index]) as page:
                width, height = page.get_size()
                if not all(math.isfinite(v) and 72 <= v <= 1584 for v in (width, height)):
                    raise Rejected('The PDF page size is unsupported.')
                if page.get_rotation():
                    raise Rejected('Rotated page layouts are not supported yet.')
                crop = page.get_bbox()
                lines = []
                with closing(page.get_textpage()) as textpage:
                    geometry, seams = text_geometry(textpage)
                    objects = 0
                    for obj in page.get_objects(max_depth=0, textpage=textpage):
                        objects += 1
                        if objects > 10000:
                            raise Rejected('This PDF is too complex to convert.')
                        if obj.type != pdf.raw.FPDF_PAGEOBJ_TEXT:
                            raise Rejected('Scans, graphics and complex layouts are not supported yet.')
                        if pdf.raw.FPDFTextObj_GetTextRenderMode(obj) != 0:
                            raise Rejected('The PDF contains text that needs visual review.')
                        matrix = obj.get_matrix()
                        rgba = [ctypes.c_uint() for _ in range(4)]
                        color_ok = pdf.raw.FPDFPageObj_GetFillColor(obj, *(ctypes.byref(v) for v in rgba))
                        if (not color_ok or rgba[3].value != 255 or min(v.value for v in rgba[:3]) > 240
                                or abs(matrix.b) > .001 or abs(matrix.c) > .001
                                or matrix.a <= 0 or matrix.d <= 0
                                or pdf.raw.FPDFClipPath_CountPaths(pdf.raw.FPDFPageObj_GetClipPath(obj)) > 0):
                            raise Rejected('The PDF contains styled or hidden text that needs visual review.')
                        value = obj.extract()
                        if not value.strip():
                            continue
                        if any(ord(c) < 32 and c not in '\n\r\t' for c in value) or '\ufffd' in value:
                            raise Rejected('The PDF text could not be read reliably.')
                        if any(unicodedata.category(c) in ('Co', 'Cn', 'Cs') or unicodedata.bidirectional(c) in ('R', 'AL') for c in value):
                            raise Rejected('This text or writing direction is not supported yet.')
                        left, bottom, right, top = obj.get_bounds()
                        if not all(math.isfinite(v) for v in (left, bottom, right, top)):
                            raise Rejected('The PDF text position needs review.')
                        if left < crop[0] - 1 or bottom < crop[1] - 1 or right > crop[2] + 1 or top > crop[3] + 1:
                            raise Rejected('The PDF contains clipped text that needs review.')
                        total += len(value)
                        if len(value) > 50000 or total > 1000000:
                            raise Rejected('The PDF contains too much text to convert.')
                        identifier = ctypes.cast(obj.raw, ctypes.c_void_p).value
                        glyphs = geometry.get(identifier)
                        if not glyphs:
                            raise Rejected('The PDF text structure needs review.')
                        em = max(glyphs[0][2][3] - glyphs[0][2][1], 1)
                        lines.append((top, bottom, left, right, value, glyphs[0][1],
                                      glyphs[0][0], glyphs[-1][2][2], em, identifier))
                if not lines:
                    raise Rejected('This PDF has a blank or scanned page. OCR is not available yet.')
                lines = readable_lines(lines, seams)
                result['pages'].append({
                    'index': index, 'width': width, 'height': height, 'rotation': 0,
                    'blocks': [{'id': f'p{index}-b{order}', 'kind': 'paragraph',
                                'bbox': [line[2] - crop[0], crop[3] - line[0],
                                         line[3] - crop[0], crop[3] - line[1]],
                                'source': 'native', 'reading_order': order,
                                'text_raw': line[4].strip()} for order, line in enumerate(lines)],
                })
    return result


def export_word(model, destination):
    if destination.suffix.lower() != '.docx' or destination.exists():
        raise Rejected('Choose a new Word output file.')
    document = Document()
    for key, relationship in list(document.part.package.rels.items()):
        if relationship.reltype.endswith('/thumbnail'):
            del document.part.package.rels[key]
    document.core_properties.author = 'Smart PDF'
    document.core_properties.last_modified_by = 'Smart PDF'
    normal = document.styles['Normal']
    normal.font.name = 'Arial'
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    for index, page in enumerate(model['pages']):
        section = document.add_section(WD_SECTION_START.NEW_PAGE) if index else document.sections[0]
        section.page_width = Pt(page['width'])
        section.page_height = Pt(page['height'])
        margin = min(36, page['width'] / 10, page['height'] / 10)
        section.left_margin = section.right_margin = Pt(margin)
        section.top_margin = section.bottom_margin = Pt(margin)
        for block in page['blocks']:
            document.add_paragraph(block['text_raw'])
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        staged = Path(directory) / 'output.docx'
        document.save(staged)
        if staged.stat().st_size > 30 * 1024**2:
            raise Rejected('The Word output exceeds the size limit.')
        if os.name == 'nt':
            os.rename(staged, destination)  # Windows rename refuses an existing destination.
        else:
            os.link(staged, destination)  # Atomic publish without replacing another result.


def convert(source, destination):
    model = parse_pdf(source)
    export_word(model, destination)
    return {'pages': len(model['pages'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(convert(args.source, args.destination)))
    except Rejected as error:
        print(json.dumps({'error': str(error), 'code': 'INPUT_REJECTED'}))
        raise SystemExit(2)
    except Exception:
        print(json.dumps({'error': 'The PDF could not be converted. Choose a valid simple text PDF.',
                          'code': 'INPUT_REJECTED'}))
        raise SystemExit(2)
