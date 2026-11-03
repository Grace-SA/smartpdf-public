"""Bounded DOCX inspection. Never extracts files, follows links or logs content."""
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

class Rejected(ValueError):
    pass

def inspect_docx(path):
    warnings = {'Fonts may be substituted. Check pagination before sharing.'}
    try:
        with zipfile.ZipFile(path) as package:
            entries = package.infolist()
            if len(entries) > 2000 or len({e.filename for e in entries}) != len(entries):
                raise Rejected('Unsupported or oversized document package.')
            total = 0
            nodes = 0
            main = None
            types = None
            for entry in entries:
                name = entry.filename
                if ('\\' in name or name.startswith('/') or '..' in PurePosixPath(name).parts
                        or entry.flag_bits & 1):
                    raise Rejected('Protected or unsafe document package.')
                total += entry.file_size
                if total > 100 * 1024**2 or entry.file_size > 30 * 1024**2 or entry.file_size > max(entry.compress_size, 1) * 200:
                    raise Rejected('Document expands beyond the processing limit.')
                lower = name.lower()
                if any(part in lower for part in ('vbaproject', 'activex/', 'embeddings/', 'customui/', 'fonts/')):
                    raise Rejected('Remove embedded files, fonts or active content in Word before converting.')
                if not (lower.endswith('.xml') or lower.endswith('.rels')):
                    continue
                if entry.file_size > 8 * 1024**2:
                    raise Rejected('Document XML exceeds the processing limit.')
                data = package.read(entry)
                # Word XML is UTF-8/16. Removing NULs also detects UTF-16 declarations.
                if re.search(br'<!\s*(DOCTYPE|ENTITY)', data.replace(b'\x00', b''), re.I):
                    raise Rejected('Document contains unsupported XML declarations.')
                tree = ET.fromstring(data)
                field_text = ''.join(''.join(e.itertext()) if e.tag.rsplit('}', 1)[-1] == 'instrText' else ' '.join(e.attrib.values())
                                     for e in tree.iter() if e.tag.rsplit('}', 1)[-1] in {'instrText', 'fldSimple'})
                if re.search(r'\b(DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|DATABASE|LINK)\b', field_text, re.I):
                    raise Rejected('Remove external data fields in Word before converting.')
                stack = [(tree, 1)]
                for element, depth in stack:
                    nodes += 1
                    if nodes > 200000 or depth > 64:
                        raise Rejected('Document structure exceeds the processing limit.')
                    stack.extend((child, depth + 1) for child in element)
                    tag = element.tag.rsplit('}', 1)[-1]
                    if tag in {'ins', 'del', 'moveFrom', 'moveTo', 'comment', 'commentRangeStart', 'vanish', 'webHidden', 'altChunk', 'object'}:
                        raise Rejected('Resolve revisions, comments, hidden content or embedded objects in Word first.')
                    if tag == 'Relationship':
                        attrs = element.attrib
                        if attrs.get('TargetMode', '').lower() == 'external':
                            kind = attrs.get('Type', '').rsplit('/', 1)[-1]
                            target = attrs.get('Target', '')
                            if kind != 'hyperlink' or not re.match(r'^(https?://|mailto:)', target, re.I):
                                raise Rejected('Embed linked content in Word before converting.')
                    if tag in {'instrText', 'fldSimple'}:
                        instruction = ''.join(element.itertext()) + ' '.join(element.attrib.values())
                        if re.search(r'\b(DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|DATABASE|LINK)\b', instruction, re.I):
                            raise Rejected('Remove external data fields in Word before converting.')
                    if tag in {'anchor', 'txbxContent', 'oMath', 'chart', 'diagram'} or (tag == 'cols' and any(k.rsplit('}', 1)[-1] == 'num' and v != '1' for k, v in element.attrib.items())):
                        warnings.add('This document contains complex layout. Check pictures, columns and equations in the preview.')
                    if tag in {'instrText', 'fldSimple'}:
                        warnings.add('Page numbers and contents may be recalculated. Check the resulting contents and links.')
                if name == 'word/document.xml':
                    main = tree
                if name == '[Content_Types].xml':
                    types = tree
            if main is None or types is None or main.tag != '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document':
                raise Rejected('Choose a valid, unencrypted DOCX document.')
            required = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
            if not any(e.attrib.get('PartName') == '/word/document.xml' and e.attrib.get('ContentType') == required for e in types):
                raise Rejected('Only standard DOCX documents are supported.')
            text = ''.join(main.itertext()).strip()
            has_media = any(e.filename.startswith('word/media/') for e in entries)
            if not text and not has_media:
                raise Rejected('The document has no visible content to convert.')
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, OSError, NotImplementedError):
        raise Rejected('Choose a valid, unencrypted DOCX document.') from None
    return sorted(warnings)
