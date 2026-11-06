"""Bounded presentation inspection. No extraction and no external resource access."""
import io
import posixpath
import re
import struct
import zipfile
from xml.etree import ElementTree as ET

P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG = '{http://schemas.openxmlformats.org/package/2006/relationships}'
CT = '{http://schemas.openxmlformats.org/package/2006/content-types}'
MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'


class Rejected(ValueError):
    pass


def fail(message='Choose a valid, unprotected PPTX presentation.'):
    raise Rejected(message)


def image_size(raw):
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        if len(raw) < 33 or raw[12:16] != b'IHDR': fail('A slide contains a damaged image.')
        return struct.unpack('>II', raw[16:24])
    if not raw.startswith(b'\xff\xd8'): fail('A slide contains a damaged image.')
    offset = 2
    while offset + 4 <= len(raw):
        if raw[offset] != 255: fail('A slide contains a damaged JPEG.')
        while offset < len(raw) and raw[offset] == 255: offset += 1
        if offset >= len(raw): break
        marker = raw[offset]; offset += 1
        if marker in (0xd8, 0x01) or 0xd0 <= marker <= 0xd7: continue
        if marker in (0xd9, 0xda): break
        length = int.from_bytes(raw[offset:offset+2], 'big')
        if length < 2 or offset + length > len(raw): break
        if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
            if length < 8: break
            height, width = struct.unpack('>HH', raw[offset+3:offset+7])
            return width, height
        offset += length
    fail('A slide contains an unsupported or damaged JPEG.')


def package_xml(data, *, workbook=False, budget=None):
    """Read all bytes with explicit aggregate limits, including nested chart data."""
    try:
        budget = budget if budget is not None else {'bytes': 0, 'nodes': 0, 'pixels': 0, 'workbooks': 0}
        package = zipfile.ZipFile(io.BytesIO(data))
        entries = package.infolist()
        if not 1 <= len(entries) <= 2500 or len({e.filename for e in entries}) != len(entries):
            fail('The presentation package has too many or duplicate entries.')
        total = 0
        trees, blobs = {}, {}
        for entry in entries:
            name = entry.orig_filename
            if name != entry.filename or chr(0) in name:
                fail('The presentation contains an unsafe package path.')
            if (entry.flag_bits & 1 or name.startswith('/') or chr(92) in name or
                    ':' in name or any(p in ('..', '.') for p in name.split('/')) or
                    entry.compress_type not in (0, 8) or len(name) > 240):
                fail()
            if entry.is_dir():
                continue
            if entry.file_size > 32 * 1024**2 or entry.file_size > max(1, entry.compress_size) * 300:
                fail('The presentation expands beyond the supported resource budget.')
            total += entry.file_size
            budget['bytes'] += entry.file_size
            if budget['bytes'] > 192 * 1024**2:
                fail('The presentation and chart data exceed the supported budget.')
            if total > (32 if workbook else 160) * 1024**2:
                fail('The presentation expands beyond the supported resource budget.')
            raw = package.read(entry)  # zipfile validates CRC; size was bounded above.
            blobs[name] = raw
            lower = name.lower()
            if any(token in lower for token in ('vbaproject', 'activex', 'oleobject', '_xmlsignatures')):
                fail('Remove macros, active objects or digital signatures before converting.')
            if lower.endswith(('.xml', '.rels')):
                if len(raw) > 8 * 1024**2 or b'<!doctype' in raw.lower() or b'<!entity' in raw.lower() or b'\x00' in raw:
                    fail('Unsupported XML content in this presentation.')
                root = ET.fromstring(raw)
                stack, nodes = [(root, 1)], 0
                while stack:
                    element, depth = stack.pop()
                    nodes += 1
                    budget['nodes'] += 1
                    if depth > 64 or nodes > 150000 or budget['nodes'] > 250000:
                        fail('The presentation XML exceeds the supported budget.')
                    stack.extend((child, depth + 1) for child in element)
                    if workbook and element.tag.rsplit('}', 1)[-1] == 'f' and re.search(r'\[|\]|\||\b(?:DDE|WEBSERVICE|RTD|CALL|REGISTER|EXEC)\s*\(', element.text or '', re.I):
                        fail('Remove external or active formulas from chart data before converting.')
                trees[name] = root
            elif lower.endswith('.xlsx') and not workbook:
                budget['workbooks'] += 1
                if budget['workbooks'] > 50: fail('Too many embedded chart workbooks.')
                package_xml(raw, workbook=True, budget=budget)
            elif re.fullmatch(r'ppt/printersettings/printersettings[0-9]+\.bin', lower) and len(raw) <= 65536:
                pass  # Passive, bounded saved printer configuration; never executed.
            elif lower.endswith(('.png', '.jpg', '.jpeg')) and not workbook:
                width, height = image_size(raw)
                budget['pixels'] += width * height
                if not width or not height or width * height > 40_000_000 or budget['pixels'] > 160_000_000:
                    fail('Slide images exceed the supported pixel budget.')
            else:
                fail('This presentation contains an unsupported embedded resource. Use PowerPoint to export it.')
        for name, root in trees.items():
            if not name.endswith('.rels'):
                continue
            base = '' if name == '_rels/.rels' else posixpath.dirname(posixpath.dirname(name))
            ids = set()
            for rel in root:
                if rel.tag != PKG + 'Relationship' or not rel.get('Id') or rel.get('Id') in ids:
                    fail()
                ids.add(rel.get('Id'))
                target, kind = rel.get('Target', ''), rel.get('Type', '').rsplit('/', 1)[-1]
                if rel.get('TargetMode') == 'External':
                    if kind != 'hyperlink' or not re.match(r'^(https?://|mailto:)', target, re.I):
                        fail('Embed linked resources and remove external data before converting.')
                    continue
                if chr(92) in target or ':' in target or not target:
                    fail()
                resolved = posixpath.normpath(posixpath.join(base, target)) if not target.startswith('/') else target[1:]
                if resolved.startswith('../') or resolved not in blobs:
                    fail('The presentation has a missing or unsafe resource relationship.')
                if kind in ('oleObject', 'control', 'audio', 'video', 'media', 'font', 'vbaProject'):
                    fail('Remove embedded media, fonts or active objects before converting.')
        types = trees.get('[Content_Types].xml')
        if types is None or types.tag != CT + 'Types':
            fail()
        for node in types:
            content = node.get('ContentType', '').lower()
            if any(term in content for term in ('macroenabled', 'vbaproject', 'activex', 'oleobject', 'digital-signature')):
                fail('Remove macros, active objects or signatures before converting.')
        if workbook and ('xl/workbook.xml' not in trees or any('/embeddings/' in n for n in blobs)):
            fail('Unsupported chart workbook.')
        return trees, blobs
    except Rejected:
        raise
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, OSError, RuntimeError, NotImplementedError):
        fail()


def inspect_pptx(path):
    data = path.read_bytes()
    if not 0 < len(data) <= 60 * 1024**2:
        fail('Choose a PPTX up to 60 MiB.')
    trees, blobs = package_xml(data)
    types = trees['[Content_Types].xml']
    if not any(n.get('PartName') == '/ppt/presentation.xml' and n.get('ContentType') == MIME for n in types):
        fail('Save a standard, macro-free PPTX before converting.')
    main, rels = trees.get('ppt/presentation.xml'), trees.get('ppt/_rels/presentation.xml.rels')
    if main is None or main.tag != P + 'presentation' or rels is None:
        fail()
    root_rels = trees.get('_rels/.rels')
    if root_rels is None or not any(r.get('Type', '').endswith('/officeDocument') and r.get('Target', '').lstrip('/') == 'ppt/presentation.xml' for r in root_rels):
        fail()
    mapping = {r.get('Id'): r for r in rels}
    slide_list = main.find(P + 'sldIdLst')
    if slide_list is None or not 1 <= len(slide_list) <= 250:
        fail('Choose a presentation with 1–250 source slides.')
    size = main.find(P + 'sldSz')
    try:
        width, height = int(size.get('cx')), int(size.get('cy'))
        if not 12700 <= width <= 182880000 or not 12700 <= height <= 182880000:
            fail()
    except (AttributeError, TypeError, ValueError):
        fail()
    visible, seen, slide_ids = 0, set(), set()
    for item in slide_list:
        rel = mapping.get(item.get(R + 'id'))
        if rel is None or not rel.get('Type', '').endswith('/slide') or rel.get('TargetMode') == 'External':
            fail()
        target = rel.get('Target', '')
        name = posixpath.normpath(posixpath.join('ppt', target)) if not target.startswith('/') else target[1:]
        if name in seen or item.get('id') in slide_ids:
            fail()
        seen.add(name)
        slide_ids.add(item.get('id'))
        slide = trees.get(name)
        if slide is None or slide.tag != P + 'sld':
            fail()
        show = slide.get('show', '1')
        if show not in ('1', 'true', '0', 'false'):
            fail()
        visible += show in ('1', 'true')
    if not 1 <= visible <= 200:
        fail('Choose a presentation with 1–200 visible slides. Hidden slides are not exported.')
    return {'slides': len(slide_list), 'visible': visible, 'width': width / 12700, 'height': height / 12700,
            'warnings': ['Fonts and complex graphics may change. Check the PDF before sharing.',
                         'Hidden slides, speaker notes and comments are not exported. Animations become static.']}
