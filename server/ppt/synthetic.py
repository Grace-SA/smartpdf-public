"""Original synthetic presentations only; contains no user document content."""
import io
import zipfile
from xml.sax.saxutils import escape

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def presentation(slides=None, width=12192000, height=6858000):
    slides = slides or [('SYNTHETIC_VISIBLE_ONE', False), ('SYNTHETIC_HIDDEN_SECRET', True), ('SYNTHETIC_VISIBLE_THREE', False)]
    files = {}
    override = ''.join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1, len(slides) + 1))
    files['[Content_Types].xml'] = f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>{override}</Types>'
    files['_rels/.rels'] = f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{R}/officeDocument" Target="ppt/presentation.xml"/></Relationships>'
    ids = ''.join(f'<p:sldId id="{255+i}" r:id="rId{i}"/>' for i in range(1, len(slides) + 1))
    files['ppt/presentation.xml'] = f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>{ids}</p:sldIdLst><p:sldSz cx="{width}" cy="{height}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    files['ppt/_rels/presentation.xml.rels'] = f'<Relationships xmlns="{PKG}">' + ''.join(f'<Relationship Id="rId{i}" Type="{R}/slide" Target="slides/slide{i}.xml"/>' for i in range(1, len(slides) + 1)) + '</Relationships>'
    for i, (text, hidden) in enumerate(slides, 1):
        files[f'ppt/slides/slide{i}.xml'] = f'''<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" show="{0 if hidden else 1}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id="2" name="Synthetic title"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="500000" y="500000"/><a:ext cx="9000000" cy="2000000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="2400"/><a:t>{escape(text)}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'''
    return pack(files)


def pack(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as package:
        for name, value in files.items():
            package.writestr(name, value)
    return output.getvalue()


if __name__ == '__main__':
    import sys
    from pathlib import Path
    Path(sys.argv[1]).write_bytes(presentation())
