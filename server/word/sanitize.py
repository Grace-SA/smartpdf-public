"""Remove selected package features from an already inspected temporary copy."""
from pathlib import Path
import posixpath
import zipfile
from xml.dom import minidom

WORD = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
RELS = 'http://schemas.openxmlformats.org/package/2006/relationships'
FONT_TAGS = {'embedRegular', 'embedBold', 'embedItalic', 'embedBoldItalic'}
COMMENT_TAGS = {'comment', 'commentRangeStart', 'commentRangeEnd', 'commentReference'}

def sanitize_copy(source, output, *, comments=False, fonts=False):
    if Path(source).resolve() == Path(output).resolve():
        raise ValueError('Original documents must not be overwritten')
    kinds = {'comments', 'commentsExtended', 'commentsExtensible', 'commentsIds', 'person', 'people'} if comments else set()
    if fonts: kinds.add('font')
    removed = set()
    with zipfile.ZipFile(source) as package:
        entries = package.infolist()
        if fonts:
            removed.update(e.filename for e in entries if 'fonts/' in e.filename.lower())
        for entry in entries:
            if not entry.filename.endswith('.rels'): continue
            doc = minidom.parseString(package.read(entry))
            owner = posixpath.dirname(posixpath.dirname(entry.filename))
            for node in doc.getElementsByTagName('*'):
                if node.namespaceURI == RELS and node.localName == 'Relationship' and node.getAttribute('Type').rsplit('/', 1)[-1] in kinds:
                    target = node.getAttribute('Target')
                    removed.add(posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(owner, target)))
            doc.unlink()
        removed.update(posixpath.join(posixpath.dirname(name), '_rels', posixpath.basename(name)+'.rels') for name in list(removed))
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as result:
            for entry in entries:
                if entry.filename in removed: continue
                data = package.read(entry)
                if entry.filename.endswith(('.xml', '.rels')):
                    doc = minidom.parseString(data)
                    for node in list(doc.getElementsByTagName('*')):
                        remove = node.namespaceURI == WORD and ((comments and node.localName in COMMENT_TAGS) or (fonts and node.localName in FONT_TAGS))
                        remove |= node.namespaceURI == RELS and node.localName == 'Relationship' and node.getAttribute('Type').rsplit('/', 1)[-1] in kinds
                        remove |= entry.filename == '[Content_Types].xml' and node.getAttribute('PartName').lstrip('/') in removed
                        if remove and node.parentNode: node.parentNode.removeChild(node)
                    data = doc.toxml(encoding='utf-8')
                    doc.unlink()
                result.writestr(entry.filename, data)
