"""Independently authored public-synthetic snapshot/format compatibility cases."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from xml.etree import ElementTree as E
from fixtures import workbook, S

root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True);cases=[]
for kind in ['shared','lookup','volatile','array','names','protection','cjk','svg','missing-cache']:
    path=root/(kind+'.xlsx');parts=workbook(path,formula=True)
    sheet=E.fromstring(parts['xl/worksheets/sheet1.xml'])
    first=next(sheet.iter(f'{{{S}}}c'))
    for child in list(first):first.remove(child)
    first.attrib.pop('t',None)
    formula=E.SubElement(first,f'{{{S}}}f');formula.text='SUM(1,2)'
    value=E.SubElement(first,f'{{{S}}}v');value.text='3'
    expected=['3'];visual='filter'
    if kind=='shared':formula.attrib.update(t='shared',si='0',ref='A1:A2')
    if kind=='lookup':
        formula.text='XLOOKUP(2,A3:A4,B3:B4)';first.set('t','str');value.text='SAVED-LOOKUP';expected=['SAVED-LOOKUP']
    if kind=='volatile':formula.text='RAND()';value.text='0.125';expected=['0.125']
    if kind=='array':formula.attrib.update(t='array',ref='A1:B1');formula.text='_xlfn.SEQUENCE(1,2,3)'
    if kind=='names':
        parts['xl/workbook.xml']=parts['xl/workbook.xml'].replace('</workbook>','<definedNames><definedName name="ReportAmount">Report!$A$1</definedName></definedNames></workbook>')
    if kind=='protection':E.SubElement(sheet,f'{{{S}}}sheetProtection',sheet='1',objects='1')
    if kind=='cjk':
        first.remove(formula);first.remove(value);first.set('t','inlineStr')
        E.SubElement(E.SubElement(first,f'{{{S}}}is'),f'{{{S}}}t').text='中文排版回归'
        expected=['中文排版回归']
        parts['xl/styles.xml']=f'<styleSheet xmlns="{S}"><fonts count="1"><font><name val="SimSun"/><sz val="11"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellXfs count="1"><xf fontId="0" fillId="0" borderId="0"/></cellXfs></styleSheet>'
        parts['[Content_Types].xml']=parts['[Content_Types].xml'].replace('</Types>','<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        parts['xl/_rels/workbook.xml.rels']=parts['xl/_rels/workbook.xml.rels'].replace('</Relationships>','<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    if kind=='svg':
        R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        E.SubElement(sheet,f'{{{S}}}drawing',{f'{{{R}}}id':'drawing'})
        parts['xl/worksheets/_rels/sheet1.xml.rels']=f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="drawing" Type="{R}/drawing" Target="../drawings/drawing1.xml"/></Relationships>'
        parts['xl/drawings/drawing1.xml']=f'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{R}"><xdr:oneCellAnchor><xdr:from><xdr:col>1</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>9</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:ext cx="1905000" cy="952500"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="Synthetic SVG"/><xdr:cNvPicPr/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="picture"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1905000" cy="952500"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>'
        parts['xl/drawings/_rels/drawing1.xml.rels']=f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="picture" Type="{R}/image" Target="../media/synthetic.svg"/></Relationships>'
        parts['xl/media/synthetic.svg']='<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100"><rect width="100" height="100" fill="#e02020"/><rect x="100" width="100" height="100" fill="#1050df"/></svg>'
        parts['[Content_Types].xml']=parts['[Content_Types].xml'].replace('</Types>','<Default Extension="svg" ContentType="image/svg+xml"/><Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>')
        visual='svg'
    if kind=='missing-cache':first.remove(value)
    parts['xl/worksheets/sheet1.xml']=E.tostring(sheet,encoding='utf-8')
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as package:
        for name,content in parts.items():
            entry=zipfile.ZipInfo(name,(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;package.writestr(entry,content)
    cases.append(dict(input=kind,sheets=[0],scale='keep',expected=expected,forbidden=['Hidden-R1-C1','Other-R1-C1'],visual=visual,expectedPages=2,expectedReject=kind=='missing-cache',sourceSha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(root/'cases.json').write_text(json.dumps(cases,indent=2));print(json.dumps({'syntheticSnapshotCases':len(cases)}))
