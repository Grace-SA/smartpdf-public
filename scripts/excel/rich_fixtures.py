"""Frozen public-synthetic compatibility cases. Authoring-only: XlsxWriter + Pillow."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import xlsxwriter
from PIL import Image, ImageDraw

root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
for kind in ['png', 'jpeg']:
    image = Image.new('RGBA' if kind == 'png' else 'RGB', (240, 100), (255, 255, 255, 0) if kind == 'png' else 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 100, 90), fill='#e02020')
    draw.rectangle((130, 10, 230, 90), fill='#1050df')
    image.save(root / ('synthetic.' + kind))

cases = []
features = ['column', 'bar', 'line', 'area', 'pie', 'doughnut', 'scatter',
            'png', 'jpeg', 'cell', 'formula', '2_color_scale', '3_color_scale', 'data_bar', 'icon_set',
            'filter', 'table', 'filtered-table', 'combined', 'chart-only']
for index, feature in enumerate(features):
    path = root / (feature + '.xlsx')
    book = xlsxwriter.Workbook(path)
    book.set_properties({'author': 'Smart PDF synthetic fixture', 'created': __import__('datetime').datetime(2026, 1, 1)})
    sheet = book.add_worksheet('Report')
    hidden = book.add_worksheet('Hidden'); hidden.write('A1', 'HIDDEN-DO-NOT-EXPORT'); hidden.hide()
    other = book.add_worksheet('Other'); other.write('A1', 'UNSELECTED-DO-NOT-EXPORT')
    sheet.set_column('A:J', 13); sheet.set_default_row(24)
    sheet.write('A1', 'RICH-' + feature.upper())
    sheet.write_row('A2', ['Category', 'Value'])
    for row, value in enumerate([10, 20, 30, 40, 50, 60], 2):
        sheet.write_row(row, 0, [f'ITEM-{row-1}', value])
    sheet.print_area('A1:J20'); sheet.fit_to_pages(1, 1)
    sheet.set_paper(9); sheet.set_landscape()
    expected = ['RICH-' + feature.upper()] + [f'ITEM-{i}' for i in range(1,7) if feature not in {'filter','filtered-table'} or i>=4]
    forbidden = ['HIDDEN-DO-NOT-EXPORT', 'UNSELECTED-DO-NOT-EXPORT']
    chart_type = feature if index < 7 else 'column'
    if index < 7 or feature in {'combined', 'chart-only'}:
        chart = book.add_chart({'type': chart_type})
        source = sheet
        if feature == 'chart-only':
            # The chart remains printable when all data is on a hidden dependency sheet.
            for row in range(1, 7): hidden.write_row(row, 0, [f'POINT-{row}', row * 10])
            source = hidden
            # Remove all cells: drawing alone must count as printable content.
            sheet.table.clear()
            expected = [f'POINT-{i}' for i in range(1,7)]
        chart.add_series({'name': 'Sales', 'categories': [source.name, 1 if source is hidden else 2, 0, 6 if source is hidden else 7, 0], 'values': [source.name, 1 if source is hidden else 2, 1, 6 if source is hidden else 7, 1], 'fill': {'color': '#E02020'}, 'line': {'color': '#1050DF'}})
        chart.set_title({'name': 'CHART-' + feature.upper()})
        chart.set_size({'width': 450, 'height': 280})
        sheet.insert_chart('D2', chart)
        expected.append('CHART-' + feature.upper())
    if feature in {'png', 'jpeg', 'combined'}:
        sheet.insert_image('D15' if feature == 'combined' else 'D3', str(root / ('synthetic.jpeg' if feature == 'jpeg' else 'synthetic.png')))
    if feature in {'cell', 'formula', '2_color_scale', '3_color_scale', 'data_bar', 'icon_set', 'combined'}:
        kind = 'cell' if feature == 'combined' else feature
        rule = {'type': kind}
        if kind in {'cell', 'formula'}:
            rule['criteria'] = '>=40' if kind == 'formula' else '>='
            if kind == 'formula': rule['criteria'] = '=$B3>=40'
            else: rule['value'] = 40
            rule['format'] = book.add_format({'bg_color': '#E02020', 'font_color': '#FFFFFF'})
        if kind == 'icon_set': rule['icon_style'] = '3_arrows'
        if kind == 'data_bar': rule['bar_color'] = '#1050DF'
        if 'color_scale' in kind: rule.update(min_color='#1050DF', max_color='#E02020')
        sheet.conditional_format('B3:B8', rule)
    if feature in {'table', 'filtered-table', 'combined'}:
        sheet.add_table('A2:B8', {'name': 'SalesTable', 'columns': [{'header': 'Category'}, {'header': 'Value'}], 'style': 'Table Style Medium 2'})
    if feature in {'filter', 'filtered-table'}:
        sheet.autofilter('A2:B8') if feature == 'filter' else None
        # Preserve the saved Excel view: the omitted records are hidden in OOXML.
        if feature == 'filter': sheet.filter_column(1, 'x >= 40')
        for row in range(2, 5): sheet.set_row(row, 24, None, {'hidden': True})
        forbidden.extend(['ITEM-1', 'ITEM-2', 'ITEM-3'])
        expected.extend(['ITEM-4', 'ITEM-5', 'ITEM-6'])
    book.close()
    # Freeze ZIP timestamps too; raw bytes, not an interchangeable regenerated sample.
    with zipfile.ZipFile(path) as package: parts = {name: package.read(name) for name in package.namelist()}
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as package:
        for name, value in parts.items():
            item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); item.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(item, value)
    cases.append(dict(input=feature, sheets=[0], scale='keep', expected=expected, forbidden=forbidden,
                      visual=feature, sourceSha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(root / 'cases.json').write_text(json.dumps(cases, indent=2))
print(json.dumps({'frozenRichCases': len(cases)}))
