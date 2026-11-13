"""Structural and text checks are diagnostic, never proof of visual fidelity."""
from collections import Counter
from difflib import SequenceMatcher
from pathlib import PurePosixPath
import re
import unicodedata
import zipfile
from pptx import Presentation
from .config import ConversionError


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if not c.isspace())


def ordered_numeric_tokens(text):
    # A grouped number must end at a valid group boundary. In a date such as
    # "January 1,1990", 1,199 is not a valid prefix of the following year.
    # Keep leading decimal points and Unicode minus signs significant too.
    number=r'[-+−]?(?:(?:\d{1,3}(?:,\d{3})+(?!\d|,\d)|\d+)(?:\.\d+)?|\.\d+)'
    # Accounting signs and separated percent marks are meaningful even when a
    # long paragraph's character-error tolerance would otherwise hide their loss.
    value=number+r'(?:[^\S\r\n]*%)?'
    pattern=r'\([^\S\r\n]*[$€£¥]?[^\S\r\n]*'+value+r'[^\S\r\n]*\)|'+value
    return [re.sub(r'\s+','',token).replace('−','-')
            for token in re.findall(pattern,unicodedata.normalize('NFKC',text))]



def numeric_tokens(text):
    return Counter(ordered_numeric_tokens(text))


def text_metrics(expected, actual):
    a, b = normalized(expected), normalized(actual)
    if not a:
        return {'reference_characters': 0, 'character_recall': None,
                'character_precision': None, 'sequence_similarity': None}
    common = sum((Counter(a) & Counter(b)).values())
    return {'reference_characters': len(a), 'character_recall': common/len(a),
            'character_precision': common/max(1, len(b)),
            'sequence_similarity': SequenceMatcher(None, a[:100000], b[:100000], autojunk=False).ratio()
            if max(len(a), len(b)) <= 20000 else None}


def shape_text(shapes):
    texts = []
    for shape in shapes:
        if shape.has_text_frame:
            texts.append(shape.text)
        if shape.has_table:
            texts.extend(c.text for row in shape.table.rows for c in row.cells)
        if hasattr(shape, 'shapes'):
            texts.extend(shape_text(shape.shapes))
    return texts


def inspect_pptx(path, info, mode):
    try:
        with zipfile.ZipFile(path) as z:
            members = z.infolist()
            if len(members) > 20000 or sum(x.file_size for x in members) > 300*1024*1024:
                raise ConversionError('unsafe_output')
            for entry in members:
                p = PurePosixPath(entry.filename)
                if '..' in p.parts or p.is_absolute() or 'vbaProject' in entry.filename:
                    raise ConversionError('unsafe_output')
                if entry.filename.endswith('.rels'):
                    from xml.etree.ElementTree import fromstring
                    xml = z.read(entry)
                    if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                        raise ConversionError('unsafe_output')
                    root = fromstring(xml)
                    if any(x.attrib.get('TargetMode') == 'External' and
                           not x.attrib.get('Type', '').endswith('/hyperlink') for x in root):
                        raise ConversionError('external_output_resource')
            if '[Content_Types].xml' not in z.namelist() or 'ppt/presentation.xml' not in z.namelist():
                raise ConversionError('invalid_pptx')
        prs = Presentation(path)
    except ConversionError:
        raise
    except Exception as e:
        raise ConversionError('invalid_pptx') from e
    if len(prs.slides) != info['page_count']:
        raise ConversionError('page_count_mismatch')
    pages, warnings = [], []
    for slide, ref in zip(prs.slides, info['pages']):
        text = '\n'.join(shape_text(slide.shapes))
        metrics = text_metrics(ref['text'], text)
        pages.append({'page': ref['number'], 'editable_characters': len(normalized(text)), **metrics})
        if mode == 'editable':
            if metrics['reference_characters'] and (metrics['character_recall'] < .995 or metrics['character_precision'] < .995):
                warnings.append({'page': ref['number'], 'code': 'text_mismatch'})
            if numeric_tokens(ref['text']) != numeric_tokens(text):
                warnings.append({'page': ref['number'], 'code': 'numeric_mismatch'})
            if metrics['sequence_similarity'] is not None and metrics['sequence_similarity'] < .98:
                warnings.append({'page': ref['number'], 'code': 'reading_order_or_text_mismatch'})
            if ref['needs_ocr_check']:
                warnings.append({'page': ref['number'], 'code': 'ocr_needs_ground_truth'})
            if '\ufffd' in text:
                warnings.append({'page': ref['number'], 'code': 'replacement_character'})
    if info['mixed_sizes']:
        warnings.append({'code': 'mixed_page_sizes'})
    if mode == 'editable':
        warnings.append({'code': 'visual_review_required'})
    return {'mode': mode, 'slide_count': len(prs.slides), 'pages': pages, 'warnings': warnings,
            'visual_validation': 'not_run', 'structure_semantics': 'not_verified',
            'verdict': 'needs_review' if mode == 'editable' else 'appearance_only'}

