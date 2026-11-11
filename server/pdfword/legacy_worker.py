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
                        value = obj.extract().strip()
                        if not value:
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
                        lines.append((top, bottom, left, right, value))
                if not lines:
                    raise Rejected('This PDF has a blank or scanned page. OCR is not available yet.')
                lines.sort(key=lambda item: (-item[0], item[2]))
                if any(a[1] < b[0] - 2 for a, b in zip(lines, lines[1:])):
                    raise Rejected('Tables, columns and overlapping text are not supported yet.')
                result['pages'].append({
                    'index': index, 'width': width, 'height': height, 'rotation': 0,
                    'blocks': [{'id': f'p{index}-b{order}', 'kind': 'paragraph',
                                'bbox': [line[2] - crop[0], crop[3] - line[0],
                                         line[3] - crop[0], crop[3] - line[1]],
                                'source': 'native', 'reading_order': order,
                                'text_raw': line[4]} for order, line in enumerate(lines)],
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
