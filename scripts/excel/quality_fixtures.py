"""Twenty-four frozen synthetic cases, including long tables and display formats."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from fixtures import workbook, S

root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
cases = []
for i in range(25):
    stem = f'case-{i:02d}'
    sheets = [('Report', 'visible'), ('Other', 'visible'), ('Hidden', 'hidden')]
    rows, cols, area = 8, 5, None
    selected, scale, orientation, paper = [0], 'keep', 'keep', 'keep'
    if i == 1: selected = [1]
    if i == 2: selected = [0, 1]
    if i in {3, 4, 5}: rows, cols = 500, 14; scale = {3:'keep',4:'width',5:'page'}[i]
    if i == 6: orientation, paper = 'landscape', 'A4'
    if i == 7: orientation, paper = 'landscape', 'Letter'
    if i in {8, 9}: area = '$A$1:$C$5'; scale = 'width'
    if i in {10, 11}: rows, cols, scale = 100, 4, 'width'
    if i in {12, 13}: rows, cols = 12, 4
    if i == 20: selected, orientation, paper, scale = [0,1], 'landscape', 'A4', 'width'
    if i == 21: rows, cols, scale, paper = 400, 2, 'width', 'Letter'
    if i == 22: sheets[2] = ('Hidden', 'veryHidden')
    if i == 23: rows, cols, scale = 8, 20, 'width'
    if i == 24: rows, cols, scale = 100, 5, 'width'
    path = root / f'{stem}.xlsx'
    parts = workbook(path, sheets=sheets, rows=rows, cols=cols, area=area, formula=i==14)
    key = 'xl/worksheets/sheet1.xml'
    xml = parts[key]
    if i == 9: parts['xl/workbook.xml'] = parts['xl/workbook.xml'].replace('Report!$A$1:$C$5', 'Report!$A$1:$C$3,Report!$A$8:$C$10')
    if i == 10: xml = xml.replace('<row r="4">', '<row r="4" hidden="1">')
    if i == 11: xml = xml.replace('<cols>', '<cols><col min="2" max="2" hidden="1" width="22" customWidth="1"/>')
    if i == 24: xml = xml.replace('<col min="1" max="5" width="22" customWidth="1"/>', '<col min="1" max="1" width="22" customWidth="1"/><col min="2" max="2" width="22" customWidth="1" hidden="1"/><col min="3" max="5" width="22" customWidth="1"/>')
    if i == 12: xml = xml.replace('Report-R1-C1', '合成报价测试，金额与日期').replace('</sheetData>', '</sheetData><mergeCells count="1"><mergeCell ref="A1:C1"/></mergeCells>')
    if i == 13: xml = xml.replace('<row r="2">', '<row r="2" ht="45" customHeight="1">').replace('Report-R2-C1', 'Long wrapped synthetic content for layout verification')
    if i in {15, 16, 17}:
        parts['xl/styles.xml'] = f'<styleSheet xmlns="{S}"><fonts count="1"><font><sz val="11"/><name val="Arial"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs></styleSheet>'
        parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace('</Types>', '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        parts['xl/_rels/workbook.xml.rels'] = parts['xl/_rels/workbook.xml.rels'].replace('</Relationships>', '<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        start = xml.index('<c r="A2"'); end = xml.index('</c>',start)+4
        value = {15:('1','1234.56'),16:('2','0.125'),17:('3','46000')}[i]
        xml = xml[:start] + f'<c r="A2" s="{value[0]}"><v>{value[1]}</v></c>' + xml[end:]
    if i == 18:
        start = xml.index('<c r="A2"'); end = xml.index('</c>',start)+4
        xml = xml[:start] + '<c r="A2"><f>SUM(Hidden!A1:A2)</f><v>0</v></c>' + xml[end:]
    if i == 19: xml = xml.replace('</worksheet>', '<rowBreaks count="1" manualBreakCount="1"><brk id="4" min="0" max="16383" man="1"/></rowBreaks></worksheet>')
    parts[key] = xml
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as package:
        for name, value in parts.items():
            item = zipfile.ZipInfo(name, (2026,1,1,0,0,0)); item.compress_type=zipfile.ZIP_DEFLATED
            package.writestr(item,value)
    cases.append(dict(input=stem,sheets=selected,scale=scale,orientation=orientation,paper=paper,expectedReject=i==11,sourceSha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(root/'cases.json').write_text(json.dumps(cases,indent=2))
print(json.dumps({'frozenSyntheticCases':len(cases)}))
