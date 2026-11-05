"""Deterministic synthetic workbooks; no user documents or third-party assets."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

def workbook(path, sheets=None, rows=8, cols=5, area=None, formula=False, active=0):
    sheets = sheets or [('Report', 'visible'), ('Other', 'visible'), ('Hidden', 'hidden')]
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + ''.join(f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(sheets))) + '</Types>',
        '_rels/.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{R}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{S}" xmlns:r="{R}"><bookViews><workbookView activeTab="{active}"/></bookViews><sheets>' + ''.join(f'<sheet name="{escape(name)}" sheetId="{i+1}" state="{state}" r:id="rId{i+1}"/>' for i, (name, state) in enumerate(sheets)) + '</sheets>' + (f'<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">Report!{area}</definedName></definedNames>' if area else '') + '</workbook>',
        'xl/_rels/workbook.xml.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i+1}" Type="{R}/worksheet" Target="worksheets/sheet{i+1}.xml"/>' for i in range(len(sheets))) + '</Relationships>',
    }
    for i, (name, _) in enumerate(sheets):
        data = []
        for row in range(1, rows + 1):
            cells = ''.join(f'<c r="{chr(65+col)}{row}" t="inlineStr"><is><t>{escape(name)}-R{row}-C{col+1}</t></is></c>' for col in range(cols))
            if formula and row == 2:
                cells = '<c r="A2"><f>SUM(1,2)</f><v>3</v></c>' + cells[cells.index('</c>')+4:]
            data.append(f'<row r="{row}">{cells}</row>')
        parts[f'xl/worksheets/sheet{i+1}.xml'] = f'<worksheet xmlns="{S}"><sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetFormatPr defaultRowHeight="20"/><cols><col min="1" max="{cols}" width="22" customWidth="1"/></cols><sheetData>{"".join(data)}</sheetData><pageMargins left="0.3" right="0.3" top="0.4" bottom="0.4" header="0.2" footer="0.2"/><pageSetup paperSize="9" orientation="portrait"/></worksheet>'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as out:
        for name, text in parts.items():
            item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(item, text)
    return parts

if __name__ == '__main__':
    import sys
    root = Path(sys.argv[1])
    root.mkdir(parents=True, exist_ok=True)
    workbook(root / 'selection.xlsx')
    workbook(root / 'wide-long.xlsx', rows=100, cols=14)
    workbook(root / 'print-area.xlsx', rows=12, cols=8, area='$A$1:$C$5')
    workbook(root / 'formulas.xlsx', formula=True)
    print(json.dumps({'syntheticWorkbooks': 4}))
