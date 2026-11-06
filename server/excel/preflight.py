"""Bounded XLSX inspection and print-only edits. Never extracts or deletes sheets."""
import json
import io
import math
import posixpath
import re
import stat
import struct
import time
import zipfile
from table_styles import materialize
from xml.etree import ElementTree as ET

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
T = 'http://schemas.openxmlformats.org/package/2006/content-types'
C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
CHARTS = {'barChart', 'lineChart', 'areaChart', 'pieChart', 'doughnutChart', 'scatterChart',
          'bar3DChart', 'line3DChart', 'area3DChart', 'pie3DChart', 'radarChart', 'bubbleChart', 'stockChart', 'surfaceChart', 'surface3DChart', 'ofPieChart'}

def automatic_layout(tree, workbook, sheet, index, styles, options, drawing=None):
    """Give unconfigured tables readable paper pages, without changing cell geometry."""
    names = workbook.find(f'{{{S}}}definedNames')
    saved_fit = tree.find(f'{{{S}}}sheetPr/{{{S}}}pageSetUpPr')
    if (tree.find(f'{{{S}}}pageSetup') is not None or
        (saved_fit is not None and saved_fit.get('fitToPage') in {'1', 'true'}) or
        any(n.get('localSheetId') == str(index) and n.get('name') in {'_xlnm.Print_Area', '_xlnm.Print_Titles'} for n in (names if names is not None else [])) or
        tree.find(f'{{{S}}}rowBreaks') is not None or tree.find(f'{{{S}}}colBreaks') is not None):
        return None
    # Include object bounds; never create a print area from cell text alone.
    if tree.find(f'{{{S}}}drawing') is not None and drawing is None:
        return None
    cells = list(tree.iter(f'{{{S}}}c'))
    if not cells: return None
    def column(ref):
        if not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}', ref or ''): reject('Invalid worksheet cell reference.')
        value = 0
        for char in re.match(r'[A-Z]+', ref)[0]: value = value * 26 + ord(char) - 64
        if value > 16384: reject('Invalid worksheet cell reference.')
        return value
    last = max(column(c.get('r')) for c in cells)
    D = '{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}'
    if drawing is not None:
        for anchor in drawing:
            if anchor.tag not in {D+'twoCellAnchor', D+'oneCellAnchor', D+'absoluteAnchor'}: return None
            for marker in [anchor.find(D+'from'), anchor.find(D+'to')]:
                if marker is not None:
                    col = int(marker.findtext(D+'col', '-1'))
                    if not 0 <= col < 16384: reject('Invalid drawing anchor.')
                    last = max(last, col + 1)
    for merge in tree.findall(f'{{{S}}}mergeCells/{{{S}}}mergeCell'):
        last = max(last, column(merge.get('ref').split(':')[-1]))
    default = tree.find(f'{{{S}}}sheetFormatPr')
    default_width = float(default.get('defaultColWidth', '8.43')) if default is not None else 8.43
    widths = [default_width] * last
    for col in tree.findall(f'{{{S}}}cols/{{{S}}}col'):
        width = 0 if col.get('hidden') == '1' else float(col.get('width', str(default_width)))
        for i in range(int(col.get('min')) - 1, min(last, int(col.get('max')))): widths[i] = width
    if not all(math.isfinite(w) and 0 <= w <= 255 for w in widths): reject('Invalid worksheet column width.')
    sizes = []; digit_width = 8.1
    if styles is not None:
        fonts = styles.find(f'{{{S}}}fonts'); xfs = styles.find(f'{{{S}}}cellXfs')
        if fonts is not None and xfs is not None:
            default_size = fonts[0].find(f'{{{S}}}sz') if len(fonts) else None
            if default_size is not None:
                value = float(default_size.get('val', '11'))
                if not math.isfinite(value) or not 0 < value <= 409: reject('Invalid worksheet font size.')
                digit_width *= max(1, value / 11)
            for cell in cells:
                if cell.find(f'{{{S}}}v') is None and cell.find(f'{{{S}}}is') is None: continue
                style = int(cell.get('s', '0'))
                if style >= len(xfs): continue
                font = int(xfs[style].get('fontId', '0'))
                size = fonts[font].find(f'{{{S}}}sz') if font < len(fonts) else None
                if size is not None:
                    value = float(size.get('val', '11'))
                    if math.isfinite(value) and value > 0: sizes.append(value)
    body_size = min(sizes) if sizes else 11
    # OOXML widths use the default font's maximum digit width; the estimate is
    # conservative and only chooses a fixed percentage, never edits cell widths.
    total = sum((w * digit_width + 5) * .75 for w in widths if w)
    if drawing is not None:
        column_points = [(w * digit_width + 5) * .75 if w else 0 for w in widths]
        for anchor in drawing:
            start = anchor.find(D+'from'); end = anchor.find(D+'to'); extent = anchor.find(D+'ext')
            if start is not None:
                left = sum(column_points[:int(start.findtext(D+'col'))]) + int(start.findtext(D+'colOff', '0')) / 12700
            else:
                position = anchor.find(D+'pos')
                if position is None: return None
                left = int(position.get('x', '0')) / 12700
            if end is not None:
                right = sum(column_points[:int(end.findtext(D+'col'))]) + int(end.findtext(D+'colOff', '0')) / 12700
            elif extent is not None:
                right = left + int(extent.get('cx', '0')) / 12700
            else: return None
            if not 0 <= left <= right <= 100000: reject('Invalid drawing extent.')
            total = max(total, right)
    margins = tree.find(f'{{{S}}}pageMargins')
    if margins is None:
        margins = ET.Element(f'{{{S}}}pageMargins', {'left': '.3', 'right': '.3', 'top': '.4', 'bottom': '.4', 'header': '.2', 'footer': '.2'})
        tail = {'headerFooter', 'rowBreaks', 'colBreaks', 'customProperties', 'cellWatches', 'ignoredErrors', 'smartTags', 'drawing', 'legacyDrawing', 'legacyDrawingHF', 'picture', 'tableParts', 'extLst'}
        position = next((i for i, c in enumerate(tree) if c.tag.rsplit('}', 1)[-1] in tail), len(tree))
        tree.insert(position, margins)
    horizontal_margin = (float(margins.get('left', '.3')) + float(margins.get('right', '.3'))) * 72
    if not math.isfinite(horizontal_margin) or not 0 <= horizontal_margin < 500: reject('Invalid worksheet page margins.')
    paper = 'Letter' if options['paper'] == 'Letter' else 'A4'
    paper_width, paper_height = (612, 792) if paper == 'Letter' else (595.28, 841.89)
    portrait = paper_width - horizontal_margin
    minimum = min(100, max(85, math.ceil(8 / (body_size * .9) * 100)))
    orientation = options['orientation'] if options['orientation'] != 'keep' else ('portrait' if total * minimum / 100 <= portrait else 'landscape')
    available = (paper_width if orientation == 'portrait' else paper_height) - horizontal_margin
    scale = max(minimum, min(100, math.floor(available / max(1, total) * 100)))
    setup = ET.Element(f'{{{S}}}pageSetup', {'paperSize': '1' if paper == 'Letter' else '9', 'orientation': orientation, 'scale': str(scale), 'fitToWidth': '0', 'fitToHeight': '0', 'pageOrder': 'downThenOver'})
    tree.insert(list(tree).index(margins) + 1, setup)
    properties = tree.find(f'{{{S}}}sheetPr')
    if properties is None:
        properties = ET.Element(f'{{{S}}}sheetPr'); tree.insert(0, properties)
    page = properties.find(f'{{{S}}}pageSetUpPr')
    if page is None: page = ET.SubElement(properties, f'{{{S}}}pageSetUpPr')
    page.set('fitToPage', '0')
    # Only infer a header for a simple first row of text, without merged title cells.
    rows = tree.findall(f'{{{S}}}sheetData/{{{S}}}row')
    first = rows[0] if rows else None
    merged_header = any(re.search(r'[A-Z]+1(?::|$)', m.get('ref', '')) for m in tree.findall(f'{{{S}}}mergeCells/{{{S}}}mergeCell'))
    if len(rows) > 20 and first is not None and first.get('r') == '1' and first.get('hidden') != '1' and len(first) >= 2 and all(c.get('t') in {'s', 'inlineStr', 'str'} for c in first) and not merged_header:
        if names is None:
            names = ET.Element(f'{{{S}}}definedNames')
            position = next((i for i, c in enumerate(workbook) if c.tag.rsplit('}', 1)[-1] in {'calcPr', 'oleSize', 'customWorkbookViews', 'pivotCaches', 'smartTagPr', 'smartTagTypes', 'webPublishing', 'fileRecoveryPr', 'webPublishObjects', 'extLst'}), len(workbook))
            workbook.insert(position, names)
        quoted = "'" + sheet.get('name').replace("'", "''") + "'!"
        titles = quoted + '$1:$1'
        if total * scale / 100 > available and widths[0] > 0:
            keys = []
            for row in rows:
                cell = next((c for c in row if re.fullmatch(r'A[1-9][0-9]*', c.get('r', ''))), None)
                if cell is None: break
                value = cell.find(f'{{{S}}}v')
                key = ''.join(n.text or '' for n in cell.iter(f'{{{S}}}t')) if cell.get('t') == 'inlineStr' else (value.text if value is not None else '')
                if not key: break
                keys.append((cell.get('t', 'n'), key))
            if len(keys) == len(rows) and len(set(keys)) == len(keys): titles += ',' + quoted + '$A:$A'
        ET.SubElement(names, f'{{{S}}}definedName', {'name': '_xlnm.Print_Titles', 'localSheetId': str(index)}).text = titles
    return f'Automatic layout applied to an unconfigured worksheet: {paper} {orientation}, {scale}% scale. Wide tables can span pages horizontally; check page order and readability.'

def image_pixels(data, suffix):
    """Bound embedded raster decoding before handing bytes to the isolated renderer."""
    width = height = 0
    if suffix == 'png' and data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 33 and data[12:16] == b'IHDR':
        if data[8:12] != b'\x00\x00\x00\r' or data[-8:] != b'IEND\xaeB`\x82':
            reject('This workbook contains a damaged PNG image.')
        width, height = struct.unpack('>II', data[16:24])
    elif suffix in {'jpg', 'jpeg'} and data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        offset = 2
        while offset < len(data):
            if data[offset] != 255: break
            while offset < len(data) and data[offset] == 255: offset += 1
            if offset >= len(data): break
            marker = data[offset]; offset += 1
            if marker in {0xD9, 0xDA}: break
            if marker in {0x01, *range(0xD0, 0xD9)}: continue
            if offset + 2 > len(data): break
            length = int.from_bytes(data[offset:offset + 2], 'big')
            if length < 2 or offset + length > len(data): break
            if marker in {0xC0, 0xC1, 0xC2} and length >= 8:
                height, width = struct.unpack('>HH', data[offset + 3:offset + 7])
                break
            offset += length
    if not width or not height:
        reject('This workbook contains a damaged or unsupported picture. Use PNG or JPEG images.')
    if width > 20000 or height > 20000 or width * height > 20000000:
        reject('A workbook picture exceeds the 20 megapixel processing limit.')
    return width * height

def svg_pixels(tree):
    if tree.tag != '{http://www.w3.org/2000/svg}svg': reject('Invalid embedded SVG picture.')
    for node in tree.iter():
        if node.tag.rsplit('}',1)[-1] in {'script','foreignObject','animate','animateTransform','animateMotion','set','filter'}:
            reject('SVG pictures must be static and self-contained.')
        for key,value in node.attrib.items():
            local=key.rsplit('}',1)[-1].lower()
            if local.startswith('on') or (local=='href' and not value.startswith('#')):
                reject('SVG pictures cannot load external content or run scripts.')
        css=(node.text or '') if node.tag.endswith('}style') else node.get('style','')
        if '@' in css or '\\' in css: reject('SVG style imports are not supported.')
        for value in [css,*node.attrib.values()]:
            for url in re.findall(r'url\s*\(([^)]*)\)',value,re.I):
                if not re.fullmatch(r'''\s*['"]?#[\w:.-]+['"]?\s*''',url): reject('SVG pictures cannot load external content.')
    box=[float(v) for v in re.split(r'[\s,]+',tree.get('viewBox','0 0 300 150').strip())]
    if len(box)!=4 or not all(math.isfinite(v) for v in box): reject('Invalid SVG dimensions.')
    def length(value,fallback):
        match=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)(px|pt|pc|mm|cm|in)?',value or '')
        return float(match[1])*{'px':1,'pt':96/72,'pc':16,'mm':96/25.4,'cm':96/2.54,'in':96,None:1}[match[2]] if match else fallback
    width,height=length(tree.get('width'),box[2]),length(tree.get('height'),box[3])
    if not 0<width<=20000 or not 0<height<=20000 or width*height>20000000: reject('SVG picture dimensions exceed the processing limit.')
    return math.ceil(width*height)

class Rejected(ValueError):
    pass

def reject(message):
    raise Rejected(message)

def known_extension(element):
    allowed = {
        '{140A7094-0E35-4892-8432-C4D2E57EDEB5}': {'workbookPr'},
        '{B58B0392-4F1F-4190-BB64-5DF3571DCE5F}': {'calcFeatures', 'feature'},
        '{D14903EA-33C4-47F7-8F05-3474C54BE107}': {'version'},
        '{05A4C25C-085E-4340-85A3-A5531E510DB2}': {'themeFamily'},
        '{EB79DEF2-80B8-43E5-95BD-54CBDDF9020C}': {'slicerStyles'},
        '{9260A510-F301-46A8-8635-F512D64BE5F5}': {'timelineStyles'},
        '{FF2B5EF4-FFF2-40B4-BE49-F238E27FC236}': {'creationId'},
        '{C3380CC4-5D6E-409C-BE32-E72D297353CC}': {'uniqueId'},
    }
    namespaces = {
        'workbookPr': 'http://schemas.microsoft.com/office/spreadsheetml/2010/11/main',
        'calcFeatures': 'http://schemas.microsoft.com/office/spreadsheetml/2018/calcfeatures',
        'feature': 'http://schemas.microsoft.com/office/spreadsheetml/2018/calcfeatures',
        'version': 'http://schemas.microsoft.com/office/spreadsheetml/2024/workbookCompatibilityVersion',
        'themeFamily': 'http://schemas.microsoft.com/office/thememl/2012/main',
        'slicerStyles': 'http://schemas.microsoft.com/office/spreadsheetml/2009/9/main',
        'timelineStyles': 'http://schemas.microsoft.com/office/spreadsheetml/2010/11/main',
        'creationId': 'http://schemas.microsoft.com/office/drawing/2014/main',
        'uniqueId': 'http://schemas.microsoft.com/office/drawing/2014/chart',
    }
    if not len(element): return False
    for child in element:
        # Recognized passive DrawingML metadata. Validate the payload vocabulary,
        # rather than treating a new Office extension GUID as executable content.
        drawing_metadata = {
            '{http://schemas.microsoft.com/office/drawing/2010/main}useLocalDpi',
            '{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip',
            '{http://schemas.microsoft.com/office/drawing/2010/main}hiddenFill',
            '{http://schemas.microsoft.com/office/drawing/2010/main}hiddenLine',
        }
        colours = {f'{{http://schemas.openxmlformats.org/drawingml/2006/main}}{tag}' for tag in ['solidFill', 'srgbClr', 'sysClr', 'schemeClr', 'tint', 'shade', 'alpha', 'lumMod', 'lumOff', 'ln', 'miter', 'headEnd', 'tailEnd', 'prstDash']}
        payload = [node for node in child.iter() if node is not child]
        if len(child) and all(node.tag in drawing_metadata | colours for node in payload) and any(node.tag in drawing_metadata for node in child):
            continue
        tags = allowed.get(child.get('uri', '').upper())
        if child.tag.rsplit('}', 1)[-1] != 'ext' or tags is None or not len(child): return False
        for node in child.iter():
            if node is child: continue
            local = node.tag.rsplit('}', 1)[-1]
            if local not in tags or node.tag != '{' + namespaces[local] + '}' + local:
                return False
    return True

def serialize(tree, original):
    # Preserve prefixes referenced by mc:Ignorable / mc:Choice Requires values.
    # ElementTree otherwise drops namespace declarations used only in attribute values.
    declarations = []
    for event, item in ET.iterparse(io.BytesIO(original), events=('start-ns', 'start')):
        if event == 'start': break
        declarations.append(item)
    rendered = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
    for prefix, uri in declarations:
        key = 'xmlns' + (':' + prefix if prefix else '')
        match = re.search(rb'\b' + re.escape(key.encode()) + rb'="([^"]*)"', rendered)
        if match:
            if match.group(1).decode() != uri: reject('Unsupported namespace aliases in workbook XML.')
        else:
            tree.set(key, uri)
    return ET.tostring(tree, encoding='utf-8', xml_declaration=True)

def settings(value):
    if not isinstance(value, dict) or set(value) - {'sheets', 'orientation', 'paper', 'scale'}:
        reject('Invalid page settings. Choose your workbook again.')
    selected = value.get('sheets')
    if not isinstance(selected, list) or not 1 <= len(selected) <= 50 or any(type(i) is not int or i < 0 or i >= 50 for i in selected) or len(set(selected)) != len(selected):
        reject('Select at least one visible worksheet.')
    for key, allowed in [('orientation', {'keep', 'portrait', 'landscape'}), ('paper', {'keep', 'A4', 'Letter'}), ('scale', {'keep', 'auto', 'width', 'page'})]:
        if value.get(key, 'keep') not in allowed:
            reject('Unsupported page settings.')
    return {**{key: 'keep' for key in ('orientation', 'paper', 'scale')}, **value}

def omit_input_validation(tree):
    validation = {f'{{{S}}}dataValidations', '{http://schemas.microsoft.com/office/spreadsheetml/2009/9/main}dataValidations'}
    changed=False
    for parent in list(tree.iter()):
        for child in list(parent):
            if child.tag in validation or (child.tag.rsplit('}',1)[-1]=='ext' and len(child) and all(node.tag in validation for node in child)):
                parent.remove(child); changed=True
    for parent in reversed(list(tree.iter())):
        for child in list(parent):
            if child.tag.rsplit('}',1)[-1]=='extLst' and not len(child):
                parent.remove(child); changed=True
    return changed

def prepare(source, output, options):
    options = settings(options)
    start = time.monotonic()
    warnings = {'Fonts and pagination may change. Check every selected sheet before sharing.'}
    try:
        with zipfile.ZipFile(source) as package:
            entries = package.infolist()
            names = {e.filename for e in entries}
            if len(entries) > 2048 or len(names) != len(entries):
                reject('Unsupported workbook package.')
            trees = {}
            contents = {}
            normalized = set()
            omitted = set()
            total = nodes = cells = pixels = pictures = charts = 0
            for entry in entries:
                name = entry.filename
                if time.monotonic() - start > 5:
                    reject('Workbook inspection exceeded its time limit.')
                if (name.startswith('/') or '\\' in name or ':' in name or any(p in {'.', '..', ''} for p in name.rstrip('/').split('/'))
                    or entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16) or entry.compress_type not in {0, 8}):
                    reject('Protected or unsafe workbook package.')
                total += entry.file_size
                if total > 150 * 1024**2 or entry.file_size > 30 * 1024**2 or entry.file_size > max(1, entry.compress_size) * 200:
                    reject('Workbook expands beyond the processing limit.')
                if name.lower().startswith('customxml/') or name.lower() == 'xl/xmlmaps.xml':
                    # XML mapping/provenance payloads are not printed. Keep the
                    # saved worksheet values and omit these unused data stores.
                    omitted.add(name)
                    continue
                if re.search(r'(vbaproject|activex|embeddings|externallinks|connections|querytables|pivot|slicer|customui|_xmlsignatures|/revisions/)', name, re.I):
                    reject('Remove macros, external data, embedded objects, signatures or advanced workbook features in Excel first.')
                if name.endswith('/'):
                    continue
                data = package.read(entry)  # CRC checked; declared sizes bounded above.
                contents[name] = data
                if len(data) != entry.file_size:
                    reject('Invalid workbook entry size.')
                svg = bool(re.fullmatch(r'xl/media/[^/]+\.svg',name,re.I))
                if not name.lower().endswith(('.xml', '.rels', '.vml')) and not svg:
                    if re.fullmatch(r'xl/printerSettings/printerSettings\d+\.bin', name) and len(data) <= 1024**2:
                        warnings.add('Printer-specific device settings are omitted. Check paper size and pagination.')
                        continue
                    image = re.fullmatch(r'xl/media/[^/]+\.(png|jpg|jpeg)', name, re.I)
                    if image:
                        pixels += image_pixels(data, image.group(1).lower())
                        pictures += 1
                        if pictures > 200 or pixels > 80000000:
                            reject('Workbook pictures exceed the image processing limit.')
                        warnings.add('Check picture placement and appearance in the PDF preview.')
                        continue
                    reject('This workbook contains unsupported binary content. Use PNG, JPEG or self-contained SVG pictures.')
                if len(data) > 20 * 1024**2 or re.search(br'<!\s*(DOCTYPE|ENTITY)', data.replace(b'\x00', b''), re.I):
                    reject('Unsupported workbook XML.')
                tree = ET.fromstring(data)
                if name.lower() == 'xl/metadata.xml':
                    kinds={node.get('name') for node in tree.findall(f'{{{S}}}metadataTypes/{{{S}}}metadataType')}
                    if kinds != {'XLDAPR'}:
                        reject('Rich linked data types are not supported. Save a plain-values copy in Excel first.')
                    # Dynamic-array calculation metadata is unnecessary after
                    # cached spill values are frozen. It is never sent to Office.
                    omitted.add(name); contents.pop(name)
                    continue
                if svg:
                    if len(data)>5*1024**2: reject('SVG picture exceeds the vector processing limit.')
                    pixels+=svg_pixels(tree); pictures+=1
                    if pictures>200 or pixels>80000000: reject('Workbook pictures exceed the image processing limit.')
                    warnings.add('Check picture placement and appearance in the PDF preview.')
                if name.lower().endswith('.vml'):
                    clients = [node for node in tree.iter() if node.tag == '{urn:schemas-microsoft-com:office:excel}ClientData']
                    if not clients or any(node.get('ObjectType') != 'Note' for node in clients):
                        reject('VML controls and embedded programs are not supported. Ordinary cell notes are supported.')
                # Data validation dropdowns constrain editing, not printed output.
                # Omit them in the print copy, including the Office 2010 form.
                if b'dataValidations' in data and omit_input_validation(tree): normalized.add(name)
                trees[name] = tree
                stack = [(tree, 1)]
                while stack:
                    element, depth = stack.pop()
                    nodes += 1
                    if nodes % 4096 == 0 and time.monotonic() - start > 5:
                        reject('Workbook inspection exceeded its time limit.')
                    if depth > 64 or nodes > 1500000:
                        reject('Workbook structure exceeds the processing limit.')
                    stack.extend((child, depth + 1) for child in element)
                    tag = element.tag.rsplit('}', 1)[-1]
                    if tag == 'extLst' and not known_extension(element):
                        reject('This workbook has unsupported extensions. Export it from Excel instead.')
                    if tag == 'revisionPtr' and (element.tag != '{http://schemas.microsoft.com/office/spreadsheetml/2014/revision}revisionPtr' or len(element)):
                        reject('Workbook revision content is not supported.')
                    if tag == 'AlternateContent':
                        leaves = [n for n in element.iter() if n is not element]
                        wrappers = {'{http://schemas.openxmlformats.org/markup-compatibility/2006}Choice', '{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback'}
                        chart_styles = {f'{{{C}}}style', '{http://schemas.microsoft.com/office/drawing/2007/8/2/chart}style'}
                        if not leaves or any(n.tag not in wrappers and n.tag != '{http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac}absPath' and not (tree.tag == f'{{{C}}}chartSpace' and n.tag in chart_styles and not len(n) and re.fullmatch(r'\d{1,4}', n.get('val', ''))) for n in leaves):
                            reject('Alternative workbook content is not supported.')
                    if tag in {'oleObject', 'control', 'webPublishItems', 'externalReference'}:
                        reject('This workbook uses protected or unsupported features. Export it from Excel instead.')
                    if tag == 'definedName':
                        expression = re.sub(r'"(?:[^"]|"")*"', '""', element.text or '')
                        if re.search(r'\[[^\]]+\].*!|\||://|\bfile:|\b(?:DDE|DDEAUTO|EXEC|REGISTER|CALL|WEBSERVICE|RTD|SQLREQUEST)\s*\(', expression, re.I):
                            reject('Externally linked or executable named expressions are not supported.')
                    if element.tag == f'{{{C}}}chart' and tree.tag == f'{{{C}}}chartSpace':
                        charts += 1
                        if charts > 100: reject('Choose a workbook with at most 100 charts.')
                        plot = element.find(f'{{{C}}}plotArea')
                        if plot is None or not any(n.tag == f'{{{C}}}{kind}' for n in plot for kind in CHARTS):
                            reject('This chart type is not supported yet. Use a standard Excel chart.')
                        warnings.add('Check chart labels, values and layout in the PDF preview.')
                    if tag == 'conditionalFormatting':
                        warnings.add('Conditional formatting may look different. Check colours, data bars and icons in the PDF preview.')
                    if tag in {'autoFilter', 'tableParts'}:
                        warnings.add('Saved filter and hidden-row settings are retained. Check the visible rows in the PDF preview.')
                    if tag == 'Relationship':
                        target = element.get('Target', '')
                        kind = element.get('Type', '').rsplit('/', 1)[-1]
                        if element.get('TargetMode', '').lower() == 'external':
                            if kind != 'hyperlink' or not re.match(r'^(https?://|mailto:)', target, re.I):
                                reject('Externally linked content is not supported.')
                            warnings.add('Hyperlinks are preserved as links; linked data is not fetched.')
                        elif target.startswith('//') or '\\' in target or ':' in target:
                            reject('Unsafe workbook relationship.')
                    if tag == 'c':
                        cells += 1
                        if cells > 200000:
                            reject('Choose a workbook with at most 200,000 cells.')
                    if element.tag == f'{{{S}}}f':
                        # Printing is a snapshot, not a spreadsheet calculation service.
                        # All cell formulas (including shared/array/volatile functions)
                        # are replaced by their saved result below, never executed.
                        warnings.add('Formula values last saved in Excel are used without recalculation. Recalculate and save in Excel before converting if needed.')
                    elif element.tag in {f'{{{C}}}f', f'{{{S}}}formula', f'{{{S}}}calculatedColumnFormula', f'{{{S}}}totalsRowFormula', '{http://schemas.microsoft.com/office/excel/2006/main}f'}:
                        formula = element.text or ''
                        if not formula or re.search(r'\[[^\]]+\].*!|://|\b(?:DDE|DDEAUTO|EXEC|REGISTER|CALL)\b|\bfile:|\b(?:WEBSERVICE|RTD|SQLREQUEST)\s*\(', formula, re.I):
                            reject('Externally linked or executable formatting/chart expressions are not supported.')
                # A missing formula cache cannot silently become zero on export.
                for cell in tree.iter(f'{{{S}}}c'):
                    if cell.find(f'{{{S}}}f') is not None:
                        cache = cell.find(f'{{{S}}}v')
                        if cache is None or (cache.text is None and cell.get('t') != 'str'):
                            reject('Save the workbook in Excel to calculate all formulas before converting.')
            workbook = trees.get('xl/workbook.xml')
            types = trees.get('[Content_Types].xml')
            rels = trees.get('xl/_rels/workbook.xml.rels')
            root_rels = trees.get('_rels/.rels')
            required = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'
            if workbook is None or workbook.tag != f'{{{S}}}workbook' or types is None or rels is None or root_rels is None:
                reject('Choose a valid unencrypted XLSX workbook.')
            declared = next((e.get('ContentType') for e in types if e.get('PartName') == '/xl/workbook.xml'), None)
            if declared is None:
                declared = next((e.get('ContentType') for e in types if e.tag == f'{{{T}}}Default' and e.get('Extension', '').lower() == 'xml'), None)
            if declared != required:
                reject('Only standard XLSX workbooks are supported.')
            if any(re.search(r'macroenabled|vbaproject|activex|externalLink', e.get('ContentType', ''), re.I) for e in types):
                reject('Active workbook content is not supported.')
            # Verify every embedded picture/chart/table dependency, not just sheet links.
            # Missing targets otherwise can silently disappear during Office import.
            for name, tree in trees.items():
                if not name.endswith('.rels'): continue
                parent = posixpath.dirname(posixpath.dirname(name)) if name != '_rels/.rels' else ''
                for rel in tree:
                    if rel.get('TargetMode', '').lower() == 'external': continue
                    target = rel.get('Target', '')
                    if target.startswith('#') and rel.get('Type', '').endswith('/hyperlink'): continue
                    resolved = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(parent, target))
                    if resolved not in names or resolved.startswith('../'):
                        reject('This workbook has a missing or invalid embedded content relationship.')
            roots = [e for e in root_rels if e.get('Type', '').endswith('/officeDocument')]
            if len(roots) != 1 or roots[0].get('Target', '').lstrip('/') != 'xl/workbook.xml':
                reject('Invalid workbook relationship.')
            relation = {}
            for rel in rels:
                key = rel.get('Id')
                target = rel.get('Target', '')
                target = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
                if key in relation or target not in names:
                    reject('Invalid workbook relationship.')
                relation[key] = (target, rel.get('Type', '').rsplit('/', 1)[-1])
            sheets = list(workbook.findall(f'{{{S}}}sheets/{{{S}}}sheet'))
            if not 1 <= len(sheets) <= 50 or max(options['sheets']) >= len(sheets):
                reject('Choose a workbook with 1–50 worksheets.')
            selected = set(options['sheets'])
            changed = {'xl/workbook.xml'} | normalized
            if omitted:
                for part in omitted: contents.pop(part,None)
                for element in list(types):
                    if element.get('PartName','').lstrip('/') in omitted: types.remove(element)
                changed.add('[Content_Types].xml')
                for name,tree in trees.items():
                    if name.endswith('.rels'):
                        parent=posixpath.dirname(posixpath.dirname(name)) if name!='_rels/.rels' else ''
                        for element in list(tree):
                            target=element.get('Target','')
                            resolved=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(parent,target))
                            if resolved in omitted: tree.remove(element); changed.add(name)
            # Freeze cached values in every dependency sheet too. No formulas,
            # shared/array formula definitions or calculation-chain triggers survive.
            for name, tree in trees.items():
                if not name.startswith('xl/worksheets/') or not name.endswith('.xml'): continue
                for cell in tree.iter(f'{{{S}}}c'):
                    if 'xl/metadata.xml' in omitted:
                        cell.attrib.pop('cm',None); cell.attrib.pop('vm',None); changed.add(name)
                    formula = cell.find(f'{{{S}}}f')
                    if formula is None: continue
                    cell.remove(formula)
                    if cell.get('t') == 'str':
                        cache = cell.find(f'{{{S}}}v'); value = cache.text or ''
                        cell.remove(cache); cell.set('t', 'inlineStr')
                        text = ET.SubElement(ET.SubElement(cell, f'{{{S}}}is'), f'{{{S}}}t')
                        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve'); text.text = value
                    if cell.get('t') == 'e': warnings.add('Saved Excel error values are preserved. Check formula errors before sharing.')
                    changed.add(name)
            for name, tree in trees.items():
                if not name.startswith('xl/tables/') or not name.endswith('.xml'): continue
                for column in tree.iter(f'{{{S}}}tableColumn'):
                    for formula in list(column):
                        if formula.tag in {f'{{{S}}}calculatedColumnFormula', f'{{{S}}}totalsRowFormula', f'{{{S}}}xmlColumnPr'}:
                            column.remove(formula); changed.add(name)
                    if 'totalsRowFunction' in column.attrib:
                        column.attrib.pop('totalsRowFunction'); changed.add(name)
            chains = {name for name in contents if name.lower() == 'xl/calcchain.xml'}
            if chains:
                for name in chains: contents.pop(name)
                for element in list(types):
                    if element.get('PartName', '').lstrip('/') in chains: types.remove(element)
                for element in list(rels):
                    if element.get('Type', '').endswith('/calcChain'): rels.remove(element)
                changed.update({'[Content_Types].xml', 'xl/_rels/workbook.xml.rels'})
            # Strip only opaque driver settings; retain the explicit portable page settings.
            printer_parts = {name for name in contents if re.fullmatch(r'xl/printerSettings/printerSettings\d+\.bin', name)}
            if printer_parts:
                declared = {e.get('PartName', '').lstrip('/') for e in types if e.get('ContentType') == 'application/vnd.openxmlformats-officedocument.spreadsheetml.printerSettings'}
                binary_default = any(e.get('Extension') == 'bin' and e.get('ContentType') == 'application/vnd.openxmlformats-officedocument.spreadsheetml.printerSettings' for e in types)
                if not binary_default and not printer_parts <= declared: reject('Invalid printer settings declaration.')
                for name in printer_parts: contents.pop(name)
                for element in list(types):
                    if element.get('PartName', '').lstrip('/') in printer_parts or (element.get('Extension') == 'bin' and binary_default): types.remove(element)
                changed.add('[Content_Types].xml')
                for name, tree in trees.items():
                    if name.endswith('.rels'):
                        for element in list(tree):
                            if element.get('Type', '').endswith('/printerSettings'):
                                tree.remove(element); changed.add(name)
            visible_content = False
            seen = set()
            sheet_names = set()
            for index, sheet in enumerate(sheets):
                if not sheet.get('name') or sheet.get('name').casefold() in sheet_names or sheet.get('state', 'visible') not in {'visible', 'hidden', 'veryHidden'}:
                    reject('Invalid worksheet names or visibility.')
                sheet_names.add(sheet.get('name').casefold())
                item = relation.get(sheet.get(f'{{{R}}}id'))
                if not item or item[1] != 'worksheet' or item[0] in seen:
                    reject('Unsupported worksheet relationship.')
                target = item[0]
                seen.add(target)
                tree = trees.get(target)
                if tree is None or tree.tag != f'{{{S}}}worksheet':
                    reject('Invalid worksheet.')
                table_parts = tree.find(f'{{{S}}}tableParts')
                if index in selected and table_parts is not None:
                    sheet_rels = trees.get(posixpath.join(posixpath.dirname(target), '_rels', posixpath.basename(target) + '.rels'))
                    table_targets = {r.get('Id'): posixpath.normpath(r.get('Target','').lstrip('/') if r.get('Target','').startswith('/') else posixpath.join(posixpath.dirname(target),r.get('Target',''))) for r in (sheet_rels if sheet_rels is not None else []) if r.get('Type', '').endswith('/table')}
                    tables = []
                    for part in table_parts:
                        table = trees.get(table_targets.get(part.get(f'{{{R}}}id'), ''))
                        if table is None or table.tag != f'{{{S}}}table': reject('Invalid table relationship.')
                        tables.append(table)
                    style_tree = trees.get('xl/styles.xml')
                    if style_tree is None: reject('Workbook table styles are missing.')
                    try:
                        materialize(style_tree, tree, tables)
                    except ValueError as error:
                        reject(str(error))
                    changed.update({target, 'xl/styles.xml'})
                if printer_parts:
                    for page in tree.findall(f'{{{S}}}pageSetup'):
                        page.attrib.pop(f'{{{R}}}id', None)
                    changed.add(target)
                intervals = sorted((int(c.get('min', '0')), int(c.get('max', '0'))) for c in tree.findall(f'{{{S}}}cols/{{{S}}}col'))
                previous = 0
                for left, right in intervals:
                    if left <= previous or right < left or right > 16384:
                        reject('Overlapping or invalid column definitions are not supported. Save a fresh copy in Excel first.')
                    previous = right
                if index not in selected:
                    sheet.set('state', 'hidden')
                    continue
                if sheet.get('state', 'visible') != 'visible':
                    reject('Hidden worksheets cannot be exported.')
                visible_content |= any(c.find(f'{{{S}}}v') is not None or c.find(f'{{{S}}}is') is not None for c in tree.iter(f'{{{S}}}c')) or tree.find(f'{{{S}}}drawing') is not None
                for view in tree.findall(f'{{{S}}}sheetViews/{{{S}}}sheetView'):
                    view.set('tabSelected', '0')
                if options['scale'] == 'auto':
                    drawing = None
                    part = tree.find(f'{{{S}}}drawing')
                    if part is not None:
                        rels = trees.get(posixpath.join(posixpath.dirname(target), '_rels', posixpath.basename(target) + '.rels'))
                        for rel in (rels if rels is not None else []):
                            if rel.get('Id') == part.get(f'{{{R}}}id') and rel.get('Type', '').endswith('/drawing'):
                                location = rel.get('Target', '')
                                drawing = trees.get(posixpath.normpath(location.lstrip('/') if location.startswith('/') else posixpath.join(posixpath.dirname(target), location)))
                    layout_warning = automatic_layout(tree, workbook, sheet, index, trees.get('xl/styles.xml'), options, drawing)
                    if layout_warning:
                        warnings.add(layout_warning); changed.update({target, 'xl/workbook.xml'})
                setup = tree.find(f'{{{S}}}pageSetup')
                page_override = options['orientation'] != 'keep' or options['paper'] != 'keep' or options['scale'] in {'width', 'page'}
                if setup is None and page_override:
                    setup = ET.Element(f'{{{S}}}pageSetup')
                    # pageSetup follows margins and precedes header/footer & breaks.
                    tail = {'headerFooter', 'rowBreaks', 'colBreaks', 'customProperties', 'cellWatches', 'ignoredErrors', 'smartTags', 'drawing', 'legacyDrawing', 'legacyDrawingHF', 'picture', 'oleObjects', 'controls', 'webPublishItems', 'tableParts', 'extLst'}
                    position = next((i for i, c in enumerate(tree) if c.tag.rsplit('}', 1)[-1] in tail), len(tree))
                    tree.insert(position, setup)
                if options['orientation'] != 'keep':
                    setup.set('orientation', options['orientation'])
                if options['paper'] != 'keep':
                    setup.set('paperSize', '9' if options['paper'] == 'A4' else '1')
                if options['scale'] in {'width', 'page'}:
                    setup.attrib.pop('scale', None)
                    setup.set('fitToWidth', '1')
                    setup.set('fitToHeight', '1' if options['scale'] == 'page' else '0')
                    properties = tree.find(f'{{{S}}}sheetPr')
                    if properties is None:
                        properties = ET.Element(f'{{{S}}}sheetPr')
                        tree.insert(0, properties)
                    page = properties.find(f'{{{S}}}pageSetUpPr')
                    if page is None:
                        page = ET.SubElement(properties, f'{{{S}}}pageSetUpPr')
                    page.set('fitToPage', '1')
                if page_override:
                    changed.add(target)
            if not visible_content:
                reject('The selected worksheets have no printable content.')
            for view in workbook.findall(f'{{{S}}}bookViews/{{{S}}}workbookView'):
                view.set('activeTab', str(min(selected)))
            if options['scale'] == 'page':
                warnings.add('Fitting a whole sheet on one page can make text very small. Zoom in before sharing.')
                warnings.add('Very large sheets can still span several pages at the minimum print scale. Check the actual page count.')
            warnings.add('Existing print areas are respected; cells outside them are not exported.')
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as result:
                for name, data in contents.items():
                    result.writestr(name, serialize(trees[name], data) if name in changed else data)
            return sorted(warnings)
    except Rejected:
        raise
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, OSError, NotImplementedError, KeyError, ValueError):
        raise Rejected('Choose a valid unencrypted XLSX workbook.') from None

if __name__ == '__main__':
    import sys
    try:
        print(json.dumps({'warnings': prepare(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))}))
    except Rejected as error:
        print(json.dumps({'error': str(error)}))
        sys.exit(2)
