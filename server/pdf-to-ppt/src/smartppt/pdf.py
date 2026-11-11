"""PDFium parsing must run in a separate, time-bounded process (not threads)."""
from pathlib import Path
from contextlib import closing
import math
import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.errors import DependencyError
from .config import ConversionError


def inspect_pdf(path: Path, max_bytes=30*1024*1024, max_pages=200):
    if not 0 < path.stat().st_size <= max_bytes:
        raise ConversionError('file_size_limit')
    with path.open('rb') as f:
        if b'%PDF-' not in f.read(1024):
            raise ConversionError('invalid_pdf')
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            raise ConversionError('encrypted_pdf')
        form = reader.trailer['/Root'].get('/AcroForm')
        if form and '/XFA' in form.get_object():
            raise ConversionError('xfa_unsupported')
        with pdfium.PdfDocument(path) as doc:
            if not 0 < len(doc) <= max_pages:
                raise ConversionError('page_limit')
            pages = []
            for i in range(len(doc)):
                with closing(doc[i]) as page:
                    w, h = page.get_size()
                    if not all(math.isfinite(n) and 1 <= n <= 14400 for n in (w, h)):
                        raise ConversionError('page_dimensions')
                    with closing(page.get_textpage()) as tp:
                        text = tp.get_text_range()
                    pages.append({'number': i+1, 'width': w, 'height': h,
                                  'text': text, 'characters': len(text.strip()),
                                  'needs_ocr_check': len(text.strip()) < 12})
            ratios = [p['width']/p['height'] for p in pages]
            return {'page_count': len(pages), 'pages': pages,
                    'mixed_sizes': max(ratios)-min(ratios) > 0.01,
                    'ocr_candidate_pages': [p['number'] for p in pages if p['needs_ocr_check']]}
    except ConversionError:
        raise
    except DependencyError as e:
        raise ConversionError('encryption_unsupported') from e
    except Exception as e:
        raise ConversionError('invalid_pdf') from e


def render_page(path, page_index, max_side=1600):
    with pdfium.PdfDocument(path) as doc:
        with closing(doc[page_index]) as page:
            scale = min(2.0, max_side / max(page.get_size()))
            with closing(page.render(scale=scale)) as bitmap:
                return bitmap.to_pil().convert('RGB').copy()
