"""Materialize OOXML table styles in a print copy; keep values/formulas untouched."""
from copy import deepcopy
from pathlib import Path
import re
import time
from xml.etree import ElementTree as ET

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
def q(name): return f'{{{S}}}{name}'
def point(ref):
    match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})', ref)
    if not match: raise ValueError('Invalid table range.')
    col = 0
    for char in match[1]: col = col * 26 + ord(char) - 64
    return col, int(match[2])
def namespace(node):
    item = deepcopy(node)
    for child in item.iter(): child.tag = q(child.tag.rsplit('}', 1)[-1])
    return item
def merge(base, overlay):
    result = deepcopy(base)
    for item in overlay:
        old = result.find(item.tag)
        if old is not None: result.remove(old)
        result.append(deepcopy(item))
    return result

def materialize(styles, sheet, tables):
    deadline = time.monotonic() + 3
    if len(tables) > 100: raise ValueError('Choose a worksheet with at most 100 tables.')
    presets = {node.tag: node for node in ET.parse(Path(__file__).with_name('table-styles.xml')).getroot()}
    fonts, fills, borders, xfs = [styles.find(q(name)) for name in ['fonts', 'fills', 'borders', 'cellXfs']]
    if any(node is None or not len(node) for node in [fonts, fills, borders, xfs]):
        raise ValueError('Workbook table styles are incomplete.')
    custom = styles.find(q('tableStyles'))
    custom_dxfs = styles.find(q('dxfs'))
    cache = {}; component_cache = {}
    def component(group, node):
        key = (id(group), ET.tostring(node))
        if key not in component_cache:
            if len(group) >= 65536: raise ValueError('Table formatting exceeds the style processing limit.')
            component_cache[key] = len(group); group.append(node)
        return str(component_cache[key])
    for table in tables:
        info = table.find(q('tableStyleInfo'))
        if info is None or not info.get('name'): continue
        preset = presets.get(info.get('name'))
        definition = next((item for item in (custom if custom is not None else []) if item.get('name') == info.get('name')), None)
        if definition is not None:
            dxfs = list(custom_dxfs) if custom_dxfs is not None else []; rules = list(definition); offset = 0
        elif preset is not None:
            dxfs = [namespace(item) for item in preset.find('dxfs')]
            rules = list(preset.find('tableStyles/tableStyle')); offset = 1
        else: raise ValueError('This custom table style is missing its definition. Save the workbook in Excel first.')
        rule = {item.get('type'): item for item in rules}
        start, end = table.get('ref', '').split(':') if ':' in table.get('ref', '') else (table.get('ref', ''),) * 2
        left, top = point(start); right, bottom = point(end)
        if right < left or bottom < top or (right-left+1)*(bottom-top+1) > 200000:
            raise ValueError('Table range exceeds the cell processing limit.')
        header = int(table.get('headerRowCount', '1')); total = int(table.get('totalsRowCount', '0'))
        if header not in {0, 1} or total not in {0, 1}: raise ValueError('Unsupported table header or total rows.')
        # Styles cannot create new document content; only existing cells are edited.
        for cell_index, cell in enumerate(sheet.iter(q('c'))):
            if cell_index % 1024 == 0 and time.monotonic() > deadline: raise ValueError('Table formatting exceeded its processing time limit.')
            col, row = point(cell.get('r', ''))
            if not (left <= col <= right and top <= row <= bottom): continue
            types = ['wholeTable']
            for axis, pos, flag in [('Column', col-left, 'showColumnStripes'), ('Row', row-top-header, 'showRowStripes')]:
                if info.get(flag, '0') in {'1', 'true'} and top+header <= row <= bottom-total:
                    first = int(rule.get('first'+axis+'Stripe', ET.Element('x')).get('size', '1'))
                    second = int(rule.get('second'+axis+'Stripe', ET.Element('x')).get('size', '1'))
                    if not 1 <= first <= 200000 or not 1 <= second <= 200000: raise ValueError('Invalid table stripe size.')
                    types.append(('first' if pos % (first+second) < first else 'second')+axis+'Stripe')
            if col == right and info.get('showLastColumn') in {'1', 'true'}: types.append('lastColumn')
            if col == left and info.get('showFirstColumn') in {'1', 'true'}: types.append('firstColumn')
            if header and row == top: types += ['headerRow'] + (['firstHeaderCell'] if col == left else []) + (['lastHeaderCell'] if col == right else [])
            if total and row == bottom: types += ['totalRow'] + (['firstTotalCell'] if col == left else []) + (['lastTotalCell'] if col == right else [])
            selected = tuple(int(rule[k].get('dxfId'))-offset for k in types if k in rule and rule[k].get('dxfId') is not None)
            base_id = int(cell.get('s', '0'))
            if base_id < 0 or base_id >= len(xfs) or any(i < 0 or i >= len(dxfs) for i in selected): raise ValueError('Invalid table style reference.')
            edges = (col == left, col == right, row == top, row == bottom)
            key = (base_id, tuple(ET.tostring(dxfs[i]) for i in selected), edges)
            if key not in cache:
                base = xfs[base_id]; xf = deepcopy(base)
                if any(not 0 <= int(base.get(name+'Id', '0')) < len(group) for name, group in [('font',fonts), ('fill',fills), ('border',borders)]): raise ValueError('Invalid cell style reference.')
                font = deepcopy(fonts[int(base.get('fontId', '0'))]); fill = deepcopy(fills[int(base.get('fillId', '0'))]); border = deepcopy(borders[int(base.get('borderId', '0'))])
                for index in selected:
                    dxf = dxfs[index]
                    if dxf.find(q('font')) is not None: font = merge(font, dxf.find(q('font')))
                    if dxf.find(q('fill')) is not None and int(base.get('fillId', '0')) < 2: fill = deepcopy(dxf.find(q('fill')))
                    if dxf.find(q('border')) is not None:
                        overlay = deepcopy(dxf.find(q('border')))
                        for side, outer, internal in zip(['left','right','top','bottom'], edges, ['vertical','vertical','horizontal','horizontal']):
                            original = overlay.find(q(side)) if outer else overlay.find(q(internal))
                            old = overlay.find(q(side))
                            if old is not None: overlay.remove(old)
                            if original is not None:
                                original = deepcopy(original); original.tag = q(side); overlay.append(original)
                        for internal in ['vertical', 'horizontal']:
                            item = overlay.find(q(internal))
                            if item is not None: overlay.remove(item)
                        border = merge(border, overlay)
                # Explicit cell font properties differing from the normal font win.
                direct = fonts[int(base.get('fontId', '0'))]
                for item in direct:
                    normal = fonts[0].find(item.tag)
                    if normal is None or ET.tostring(normal) != ET.tostring(item): font = merge(font, [item])
                for name, group, value in [('Font',fonts,font), ('Fill',fills,fill), ('Border',borders,border)]:
                    xf.set(name.lower()+'Id', component(group, value)); xf.set('apply'+name, '1')
                if len(xfs) >= 65536 or len(cache) >= 4096: raise ValueError('Table formatting exceeds the style processing limit.')
                cache[key] = len(xfs); xfs.append(xf)
            cell.set('s', str(cache[key]))
    for group in [fonts, fills, borders, xfs]: group.set('count', str(len(group)))
