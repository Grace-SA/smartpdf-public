"""Public synthetic layout contracts; never reads or derives data from user files."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from xml.sax.saxutils import escape
from fixtures import workbook, S, R

root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
specs = [
    ('quotation', 24, 5, 14), ('financial-report', 40, 8, 12),
    ('payroll', 100, 14, 12), ('attendance', 35, 32, 3),
    ('inventory', 300, 8, 12), ('long-ledger', 5000, 8, 12),
    ('wide-comparison', 100, 24, 12), ('wrapped-notes', 25, 4, 24),
    ('filtered-register', 100, 6, 12), ('multiple-sheets', 30, 8, 12),
    ('saved-print-area', 30, 8, 12), ('merged-form', 25, 5, 14),
]
if '--large-only' in sys.argv[2:]: specs = [('large-ledger', 20000, 6, 12)]
def column(number):
    result = ''
    while number: number, digit = divmod(number - 1, 26); result = chr(65 + digit) + result
    return result
cases = []
for stem, count, columns, width in specs:
    path = root / (stem + '.xlsx')
    sheet_count = 1 if stem == 'large-ledger' else 3
    parts = workbook(path, rows=1, cols=1, sheets=[('Report', 'visible')] if sheet_count == 1 else None)
    expected = []; forbidden = []
    for sheet in range(1, sheet_count + 1):
        rows = []
        for row in range(1, count + 1):
            cells = []
            hidden = stem == 'filtered-register' and row > 1 and row % 3 == 0
            for col in range(1, columns + 1):
                text = f'COL-{col:02}' if row == 1 else f'T{row:05}-{col:02}'
                if sheet != 1: text = f'S{sheet}-{text}'
                if stem in {'quotation', 'merged-form'} and row == 1:
                    if col > 1: continue
                    text = '报价单 SYNTHETIC-ORDER' if sheet == 1 else f'S{sheet}-ORDER'
                if stem == 'attendance' and col > 1: text = f'{col:02}' if row == 1 else ('P' if row % 2 else 'A')
                if stem == 'wrapped-notes' and col == 4 and row > 1: text += ' wrapped note / second line / final line'
                numeric = stem in {'quotation', 'financial-report', 'payroll'} and row == 2 and col in {2, 3, 4, 5}
                if numeric:
                    style, value, text = {2:(3,'1234.5','USD1,234.50'),3:(3,'1357.95','USD1,357.95'),4:(5,'46000','2025-12-09'),5:(4,'0.125','12.50%')}[col]
                    formula = '<f>B2*1.1</f>' if col == 3 else ''
                    cells.append(f'<c r="{column(col)}{row}" s="{style}">{formula}<v>{value}</v></c>')
                else:
                    cells.append(f'<c r="{column(col)}{row}" s="{1 if row == 1 else 2 if stem == "wrapped-notes" else 0}" t="inlineStr"><is><t>{escape(text)}</t></is></c>')
                visible = sheet in ([1, 2] if stem == 'multiple-sheets' else [1]) and not hidden
                if stem == 'saved-print-area' and (row > 12 or col > 5): visible = False
                (expected if visible else forbidden).append(text)
            rows.append(f'<row r="{row}"'+(' hidden="1"' if hidden else '')+(f' ht="48" customHeight="1"' if stem == 'wrapped-notes' else '')+'>'+''.join(cells)+'</row>')
        cols = f'<col min="1" max="{columns}" width="{width}" customWidth="1"/>'
        if stem == 'attendance': cols = f'<col min="1" max="1" width="12" customWidth="1"/><col min="2" max="{columns}" width="3" customWidth="1"/>'
        tail = f'<mergeCells count="1"><mergeCell ref="A1:{column(columns)}1"/></mergeCells>' if stem in {'quotation', 'merged-form'} else ''
        if stem == 'filtered-register': tail += f'<autoFilter ref="A1:F{count}"/>'
        if stem == 'saved-print-area': tail += '<pageMargins left=".3" right=".3" top=".4" bottom=".4" header=".2" footer=".2"/><pageSetup paperSize="9" orientation="portrait"/>'
        parts[f'xl/worksheets/sheet{sheet}.xml'] = f'<worksheet xmlns="{S}"><sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetFormatPr defaultRowHeight="15"/><cols>{cols}</cols><sheetData>'+''.join(rows)+'</sheetData>'+tail+'</worksheet>'
    if stem == 'saved-print-area': parts['xl/workbook.xml'] = parts['xl/workbook.xml'].replace('</workbook>', '<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">Report!$A$1:$E$12</definedName></definedNames></workbook>')
    parts['xl/styles.xml'] = f'<styleSheet xmlns="{S}"><fonts count="2"><font><sz val="11"/><name val="Liberation Sans"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Liberation Sans"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF204E78"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf></cellXfs></styleSheet>'
    parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace('</Types>', '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
    parts['xl/styles.xml'] = parts['xl/styles.xml'].replace('<fonts count="2">', '<numFmts count="2"><numFmt numFmtId="164" formatCode="&quot;USD&quot;#,##0.00"/><numFmt numFmtId="165" formatCode="yyyy-mm-dd"/></numFmts><fonts count="2">').replace('<cellXfs count="3">', '<cellXfs count="6">').replace('</cellXfs>', ''.join(f'<xf numFmtId="{n}" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' for n in (164,10,165))+'</cellXfs>')
    parts['xl/_rels/workbook.xml.rels'] = parts['xl/_rels/workbook.xml.rels'].replace('</Relationships>', f'<Relationship Id="styles" Type="{R}/styles" Target="styles.xml"/></Relationships>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in parts.items():
            item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); item.compress_type = zipfile.ZIP_DEFLATED; z.writestr(item, value)
    # Repeated attendance status strings are valid on hidden rows too; only unique
    # marker exclusions can prove selected/hidden content did not leak.
    expected = sorted(set(expected)); forbidden = sorted(set(forbidden) - set(expected))
    cases.append({'input': stem, 'sheets': [0, 1] if stem == 'multiple-sheets' else [0], 'scale': 'auto', 'sourceSha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'expected': expected, 'forbidden': forbidden, 'maxPages': 500 if stem == 'large-ledger' else 200, 'minMedianFont': 8, 'repeatHeader': stem in {'payroll', 'inventory', 'long-ledger', 'large-ledger', 'wide-comparison', 'filtered-register', 'wrapped-notes'}, 'repeatKeyColumn': stem in {'payroll', 'wide-comparison'}, 'singlePanelColumns': columns if stem in {'financial-report','attendance','inventory','long-ledger','large-ledger','wrapped-notes','multiple-sheets'} else None})
(root / 'cases.json').write_text(json.dumps(cases, indent=2), encoding='utf-8')
print(json.dumps({'typicalLayoutCases': len(cases)}))
