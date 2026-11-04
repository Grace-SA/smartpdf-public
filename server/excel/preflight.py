"""Bounded XLSX inspection and print-only edits. Never extracts or deletes sheets."""
import json
import io
import posixpath
import re
import stat
import time
import zipfile
from xml.etree import ElementTree as ET

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
T = 'http://schemas.openxmlformats.org/package/2006/content-types'

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
    }
    namespaces = {
        'workbookPr': 'http://schemas.microsoft.com/office/spreadsheetml/2010/11/main',
        'calcFeatures': 'http://schemas.microsoft.com/office/spreadsheetml/2018/calcfeatures',
        'feature': 'http://schemas.microsoft.com/office/spreadsheetml/2018/calcfeatures',
        'version': 'http://schemas.microsoft.com/office/spreadsheetml/2024/workbookCompatibilityVersion',
        'themeFamily': 'http://schemas.microsoft.com/office/thememl/2012/main',
        'slicerStyles': 'http://schemas.microsoft.com/office/spreadsheetml/2009/9/main',
        'timelineStyles': 'http://schemas.microsoft.com/office/spreadsheetml/2010/11/main',
    }
    if not len(element): return False
    for child in element:
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
    for key, allowed in [('orientation', {'keep', 'portrait', 'landscape'}), ('paper', {'keep', 'A4', 'Letter'}), ('scale', {'keep', 'width', 'page'})]:
        if value.get(key, 'keep') not in allowed:
            reject('Unsupported page settings.')
    return {**{key: 'keep' for key in ('orientation', 'paper', 'scale')}, **value}

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
            total = nodes = cells = 0
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
                if re.search(r'(vbaproject|activex|embeddings|externallinks|connections|querytables|pivot|slicer|vml|customui|customxml|_xmlsignatures|metadata\.xml|/revisions/)', name, re.I):
                    reject('Remove macros, external data, embedded objects, signatures or advanced workbook features in Excel first.')
                if name.endswith('/'):
                    continue
                data = package.read(entry)  # CRC checked; declared sizes bounded above.
                contents[name] = data
                if len(data) != entry.file_size:
                    reject('Invalid workbook entry size.')
                if not name.lower().endswith(('.xml', '.rels')):
                    if re.fullmatch(r'xl/printerSettings/printerSettings\d+\.bin', name) and len(data) <= 1024**2:
                        warnings.add('Printer-specific device settings are omitted. Check paper size and pagination.')
                        continue
                    reject('Embedded pictures and binary workbook content are not supported yet. Export from Excel instead.')
                if len(data) > 20 * 1024**2 or re.search(br'<!\s*(DOCTYPE|ENTITY)', data.replace(b'\x00', b''), re.I):
                    reject('Unsupported workbook XML.')
                tree = ET.fromstring(data)
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
                        if not leaves or any(n.tag.rsplit('}', 1)[-1] not in {'Choice', 'absPath'} for n in leaves):
                            reject('Alternative workbook content is not supported.')
                    if tag in {'oleObject', 'control', 'webPublishItems', 'externalReference', 'sheetProtection', 'workbookProtection'}:
                        reject('This workbook uses protected or unsupported features. Export it from Excel instead.')
                    if tag == 'definedName' and element.get('name') not in {'_xlnm.Print_Area', '_xlnm.Print_Titles'}:
                        reject('Custom named ranges and formulas are not supported yet. Export from Excel instead.')
                    if tag in {'chart', 'conditionalFormatting', 'drawing', 'autoFilter', 'tableParts'}:
                        reject('Charts, pictures, conditional formatting and filtered tables are not supported yet. Export from Excel instead.')
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
                    if tag == 'f':
                        formula = element.text or ''
                        if element.attrib or not formula or re.search(r'[\[\]|]|://|\b(?:DDE|DDEAUTO|EXEC|REGISTER|CALL)\b|\bfile:|\b(?:NOW|TODAY|RAND|RANDBETWEEN|INDIRECT|OFFSET|WEBSERVICE|HYPERLINK)\s*\(', formula, re.I):
                            reject('This workbook has unsupported or volatile formulas. Save a values-only copy in Excel first.')
                        functions = re.findall(r'([A-Z_][A-Z0-9_.]*)\s*\(', formula.upper())
                        if any(f not in {'SUM', 'AVERAGE', 'MIN', 'MAX', 'COUNT', 'COUNTA', 'IF', 'IFERROR', 'ROUND', 'ROUNDUP', 'ROUNDDOWN', 'ABS', 'AND', 'OR', 'NOT', 'SUMIF', 'COUNTIF'} for f in functions):
                            reject('This formula is not supported. Save a values-only copy in Excel first.')
                        warnings.add('Formulas may be recalculated by LibreOffice. Verify totals and dates against Excel.')
                # A missing formula cache cannot silently become zero on export.
                for cell in tree.iter(f'{{{S}}}c'):
                    if cell.find(f'{{{S}}}f') is not None:
                        cache = cell.find(f'{{{S}}}v')
                        if cache is None or cache.text is None or cell.get('t') == 'e':
                            reject('Save the workbook in Excel to calculate all formulas before converting.')
            workbook = trees.get('xl/workbook.xml')
            types = trees.get('[Content_Types].xml')
            rels = trees.get('xl/_rels/workbook.xml.rels')
            root_rels = trees.get('_rels/.rels')
            required = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'
            if workbook is None or workbook.tag != f'{{{S}}}workbook' or types is None or rels is None or root_rels is None:
                reject('Choose a valid unencrypted XLSX workbook.')
            if not any(e.get('PartName') == '/xl/workbook.xml' and e.get('ContentType') == required for e in types):
                reject('Only standard XLSX workbooks are supported.')
            if any(re.search(r'macroenabled|vbaproject|activex|externalLink', e.get('ContentType', ''), re.I) for e in types):
                reject('Active workbook content is not supported.')
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
            changed = {'xl/workbook.xml'}
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
                setup = tree.find(f'{{{S}}}pageSetup')
                if setup is None and any(options[k] != 'keep' for k in ('orientation', 'paper', 'scale')):
                    setup = ET.Element(f'{{{S}}}pageSetup')
                    # pageSetup follows margins and precedes header/footer & breaks.
                    tail = {'headerFooter', 'rowBreaks', 'colBreaks', 'customProperties', 'cellWatches', 'ignoredErrors', 'smartTags', 'drawing', 'legacyDrawing', 'legacyDrawingHF', 'picture', 'oleObjects', 'controls', 'webPublishItems', 'tableParts', 'extLst'}
                    position = next((i for i, c in enumerate(tree) if c.tag.rsplit('}', 1)[-1] in tail), len(tree))
                    tree.insert(position, setup)
                if options['orientation'] != 'keep':
                    setup.set('orientation', options['orientation'])
                if options['paper'] != 'keep':
                    setup.set('paperSize', '9' if options['paper'] == 'A4' else '1')
                if options['scale'] != 'keep':
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
                if any(options[k] != 'keep' for k in ('orientation', 'paper', 'scale')):
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
