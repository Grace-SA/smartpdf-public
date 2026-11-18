"""Preserve bounded, read-only signature appearances in a temporary derivative."""
from contextlib import closing
from pathlib import Path
import math
import pypdfium2 as pdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import StreamObject
from PIL import ImageChops
from model import Rejected

NOTICE = "Signature appearance retained. The Word file does not retain PDF signature verification."


def signature_widgets(reader):
    try:
        return _signature_widgets(reader)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return set()


def _signature_widgets(reader):
    form = reader.trailer['/Root'].get('/AcroForm')
    if not form:
        return set()
    form = form.get_object()
    fields = form.get('/Fields', [])
    if not fields or len(fields) > 16 or form.get('/XFA') or form.get('/NeedAppearances'):
        return set()
    approved = set()
    for ref in fields:
        field = ref.get_object()
        if (field.get('/FT') != '/Sig' or field.get('/Subtype') != '/Widget'
                or int(field.get('/Ff', 0)) & 1 != 1
                or any(k in field for k in ('/Kids', '/A', '/AA', '/Parent'))
                or not field.get('/V')):
            return set()
        appearance = field.get('/AP', {}).get_object() if field.get('/AP') else {}
        normal = appearance.get('/N')
        if normal is None or not isinstance(normal.get_object(), StreamObject):
            return set()
        bounds = field.get('/Rect', [])
        if (len(bounds) != 4 or any(not math.isfinite(float(v)) for v in bounds)
                or not 0 < float(bounds[2]-bounds[0]) <= 1584
                or not 0 < float(bounds[3]-bounds[1]) <= 1584
                or int(field.get('/F', 0)) & (1 | 2 | 32)):
            return set()
        approved.add(id(field))
    found = [id(ref.get_object()) for page in reader.pages for ref in page.get('/Annots', [])
             if ref.get_object().get('/Subtype') == '/Widget']
    return approved if len(found) == len(approved) and set(found) == approved else set()


def flatten_signatures(source, work):
    reader = PdfReader(source, strict=True)
    approved = signature_widgets(reader)
    if not approved:
        return source, False
    affected = [i for i,p in enumerate(reader.pages)
                if any(id(a.get_object()) in approved for a in p.get('/Annots', []))]
    raw, output = Path(work)/'signatures-raw.pdf', Path(work)/'signatures-static.pdf'
    originals = {}
    with pdf.PdfDocument(source) as doc:
        doc.init_forms()
        for index in affected:
            with closing(doc[index]) as page:
                if any(not 72 <= v <= 1584 for v in page.get_size()):
                    raise Rejected('Unsupported page dimensions.')
                originals[index] = page.render(scale=1, draw_annots=True).to_pil().copy()
                page.flatten()
        doc.save(raw)
    writer = PdfWriter(clone_from=raw)
    if any(a.get_object().get('/Subtype') == '/Widget'
           for p in writer.pages for a in p.get('/Annots', [])):
        raise Rejected('Signature appearance could not be preserved.')
    writer._root_object.pop('/AcroForm', None)
    writer._root_object.pop('/Perms', None)
    writer.write(output)
    with pdf.PdfDocument(output) as doc:
        for index, before in originals.items():
            with closing(doc[index]) as page:
                after = page.render(scale=1, draw_annots=True).to_pil()
                if before.size != after.size or ImageChops.difference(before, after).getbbox():
                    raise Rejected('Signature appearance could not be preserved.')
    return output, True
