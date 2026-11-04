"""Bounded DOCX inspection. Never extracts files, follows links or logs content."""
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

WORD = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
REASONS = {
    'TRACKED_CHANGES': 'Accept or reject tracked changes in Word before converting.',
    'COMMENTS': 'Remove document comments in Word before converting.',
    'HIDDEN_TEXT': 'Show or remove hidden text in Word before converting.',
    'MACROS': 'Save a macro-free DOCX in Word before converting.',
    'ACTIVE_CONTENT': 'Remove ActiveX controls or custom active content in Word before converting.',
    'EMBEDDED_OBJECTS': 'Remove embedded files or objects in Word before converting.',
    'EMBEDDED_FONTS': 'Save a copy without embedded fonts in Word before converting.',
    'EXTERNAL_CONTENT': 'Embed linked content or remove linked templates in Word before converting.',
    'EXTERNAL_DATA_FIELDS': 'Remove external data fields in Word before converting.',
}
REVISION_TAGS = {
    'ins', 'del', 'delText', 'moveFrom', 'moveTo', 'moveFromRangeStart',
    'moveFromRangeEnd', 'moveToRangeStart', 'moveToRangeEnd', 'rPrChange',
    'pPrChange', 'tblPrChange', 'trPrChange', 'tcPrChange', 'sectPrChange',
    'tblGridChange', 'numberingChange', 'cellIns', 'cellDel', 'cellMerge',
}

class Rejected(ValueError):
    """Only fixed product messages; never package names, XML or document text."""
    def __init__(self, message, code='INVALID_DOCX', reasons=None):
        self.code = code
        self.reasons = reasons or [{'code': code, 'message': message}]
        super().__init__(message)

def reject(message, code):
    raise Rejected(message, code)

def inspect_docx(path):
    warnings = {'Fonts may be substituted. Check pagination before sharing.'}
    blocked = set()
    try:
        with zipfile.ZipFile(path) as package:
            entries = package.infolist()
            if len(entries) > 2000 or len({e.filename for e in entries}) != len(entries):
                reject('Unsupported or oversized document package.', 'PACKAGE_ENTRY_LIMIT')
            total = 0
            nodes = 0
            main = None
            types = None
            for entry in entries:
                name = entry.filename
                if ('\\' in name or name.startswith('/') or '..' in PurePosixPath(name).parts
                        or entry.flag_bits & 1):
                    reject('Protected or unsafe document package.', 'UNSAFE_PACKAGE')
                total += entry.file_size
                if total > 100 * 1024**2 or entry.file_size > 30 * 1024**2 or entry.file_size > max(entry.compress_size, 1) * 200:
                    reject('Document expands beyond the processing limit.', 'PACKAGE_EXPANSION_LIMIT')
                lower = name.lower()
                if 'vbaproject' in lower:
                    blocked.add('MACROS')
                if any(part in lower for part in ('activex/', 'customui/')):
                    blocked.add('ACTIVE_CONTENT')
                if 'embeddings/' in lower:
                    blocked.add('EMBEDDED_OBJECTS')
                if 'fonts/' in lower:
                    blocked.add('EMBEDDED_FONTS')
                if not (lower.endswith('.xml') or lower.endswith('.rels')):
                    continue
                if entry.file_size > 8 * 1024**2:
                    reject('Document XML exceeds the processing limit.', 'XML_SIZE_LIMIT')
                data = package.read(entry)
                # Word XML is UTF-8/16. Removing NULs also detects UTF-16 declarations.
                if re.search(br'<!\s*(DOCTYPE|ENTITY)', data.replace(b'\x00', b''), re.I):
                    reject('Document contains unsupported XML declarations.', 'XML_DECLARATION')
                tree = ET.fromstring(data)
                field_text = ''.join(''.join(e.itertext()) if e.tag.rsplit('}', 1)[-1] == 'instrText' else ' '.join(e.attrib.values())
                                     for e in tree.iter() if e.tag.rsplit('}', 1)[-1] in {'instrText', 'fldSimple'})
                if re.search(r'\b(DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|DATABASE|LINK)\b', field_text, re.I):
                    blocked.add('EXTERNAL_DATA_FIELDS')
                stack = [(tree, 1)]
                for element, depth in stack:
                    nodes += 1
                    if nodes > 200000 or depth > 64:
                        reject('Document structure exceeds the processing limit.', 'STRUCTURE_LIMIT')
                    stack.extend((child, depth + 1) for child in element)
                    tag = element.tag.rsplit('}', 1)[-1]
                    if element.tag.startswith(WORD):
                        if tag in REVISION_TAGS:
                            blocked.add('TRACKED_CHANGES')
                        if tag in {'comment', 'commentRangeStart', 'commentRangeEnd', 'commentReference'}:
                            blocked.add('COMMENTS')
                        # webHidden affects web view, not normal paginated/PDF view.
                        # An off vanish does not introduce hidden text. Other on
                        # declarations in defaults, styles or content still reject.
                        if tag == 'vanish' and element.get(WORD + 'val') not in {'0', 'false', 'off'}:
                            blocked.add('HIDDEN_TEXT')
                        if tag in {'altChunk', 'object'}:
                            blocked.add('EMBEDDED_OBJECTS')
                    if tag == 'Relationship':
                        attrs = element.attrib
                        if attrs.get('TargetMode', '').lower() == 'external':
                            kind = attrs.get('Type', '').rsplit('/', 1)[-1]
                            target = attrs.get('Target', '')
                            if kind != 'hyperlink' or not re.match(r'^(https?://|mailto:)', target, re.I):
                                blocked.add('EXTERNAL_CONTENT')
                    if tag in {'instrText', 'fldSimple'}:
                        instruction = ''.join(element.itertext()) + ' '.join(element.attrib.values())
                        if re.search(r'\b(DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|DATABASE|LINK)\b', instruction, re.I):
                            blocked.add('EXTERNAL_DATA_FIELDS')
                    if tag in {'anchor', 'txbxContent', 'oMath', 'chart', 'diagram'} or (tag == 'cols' and any(k.rsplit('}', 1)[-1] == 'num' and v != '1' for k, v in element.attrib.items())):
                        warnings.add('This document contains complex layout. Check pictures, columns and equations in the preview.')
                    if tag in {'instrText', 'fldSimple'}:
                        warnings.add('Page numbers and contents may be recalculated. Check the resulting contents and links.')
                if name == 'word/document.xml':
                    main = tree
                if name == '[Content_Types].xml':
                    types = tree
            if main is None or types is None or main.tag != '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document':
                reject('Choose a valid, unencrypted DOCX document.', 'INVALID_DOCX')
            required = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
            if not any(e.attrib.get('PartName') == '/word/document.xml' and e.attrib.get('ContentType') == required for e in types):
                reject('Only standard DOCX documents are supported.', 'UNSUPPORTED_DOCX_TYPE')
            text = ''.join(main.itertext()).strip()
            has_media = any(e.filename.startswith('word/media/') for e in entries)
            if not text and not has_media and not blocked:
                reject('The document has no visible content to convert.', 'EMPTY_DOCUMENT')
    except ET.ParseError:
        raise Rejected('The document contains malformed XML. Open it in Word and save a new DOCX copy.', 'MALFORMED_XML') from None
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError):
        raise Rejected('Choose a valid, unencrypted DOCX document.') from None
    if blocked:
        reasons = [{'code': code, 'message': message} for code, message in REASONS.items() if code in blocked]
        raise Rejected(' '.join(r['message'] for r in reasons), reasons[0]['code'], reasons)
    return sorted(warnings)
