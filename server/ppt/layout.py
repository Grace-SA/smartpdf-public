"""Preserve explicit OOXML no-wrap/autogrow intent after Impress import.

Input has already passed preflight. Ambiguous or changed text is not repaired.
"""
import collections
import posixpath
import zipfile
from xml.etree import ElementTree as ET

P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def normalized(text):
    return ''.join(text.split())


def nowrap_plan(source):
    result = []
    with zipfile.ZipFile(source) as package:
        main = ET.fromstring(package.read('ppt/presentation.xml'))
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(package.read('ppt/_rels/presentation.xml.rels'))}
        for slide in main.find(P + 'sldIdLst'):
            target = rels[slide.get(R + 'id')]
            path = posixpath.normpath(posixpath.join('ppt', target)) if not target.startswith('/') else target[1:]
            tree = ET.fromstring(package.read(path))
            counts = collections.Counter(n.get('name') for n in tree.iter(P + 'cNvPr'))
            wanted = {}
            for shape in tree.iter(P + 'sp'):
                body = shape.find(P + 'txBody/' + A + 'bodyPr')
                name = shape.find(P + 'nvSpPr/' + P + 'cNvPr')
                if (body is None or name is None or body.get('wrap') != 'none'
                        or body.find(A + 'spAutoFit') is None):
                    continue
                name = name.get('name')
                text = normalized(''.join(n.text or '' for n in shape.iter(A + 't')))
                if name and text and counts[name] == 1:
                    wanted[name] = text
            result.append(wanted)
    return result


def apply_no_wrap(document, source):
    plans = nowrap_plan(source)
    pages = document.getDrawPages()
    if len(plans) != pages.Count:
        raise RuntimeError('Slide layout scope differs')
    changed = 0
    for index, wanted in enumerate(plans):
        if not wanted:
            continue
        shapes = []
        def visit(container, depth=0):
            if depth > 32:
                raise RuntimeError('Text layout nesting exceeds budget')
            for i in range(container.Count):
                shape = container.getByIndex(i)
                shapes.append(shape)
                if len(shapes) > 20000:
                    raise RuntimeError('Text layout shapes exceed budget')
                if shape.supportsService('com.sun.star.drawing.GroupShape'):
                    visit(shape, depth + 1)
        visit(pages.getByIndex(index))
        counts = collections.Counter(shape.Name for shape in shapes)
        for shape in shapes:
            if shape.Name not in wanted or counts[shape.Name] != 1:
                continue
            if not shape.getPropertySetInfo().hasPropertyByName('TextAutoGrowWidth'):
                continue
            if normalized(shape.getString()) != wanted[shape.Name]:
                continue
            if not shape.TextAutoGrowWidth:
                shape.TextAutoGrowWidth = True
                changed += 1
    return changed
