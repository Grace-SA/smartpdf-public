"""Independent PyMuPDF checks of frozen source markers and selected print regions."""
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
from xml.etree import ElementTree as ET
import pymupdf
from PIL import Image, ImageDraw

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
root = Path(sys.argv[1]); cases = json.loads((root/'cases.json').read_text())
results=[]
engine = {r['case']: r for r in json.loads((root/'engine-results.json').read_text())}
def cellpos(ref):
    letters, row = re.fullmatch(r'([A-Z]+)([0-9]+)', ref.replace('$','')).groups()
    col=0
    for c in letters: col=26*col+ord(c)-64
    return col,int(row)
def rectangle(value):
    a,b=value.split(':') if ':' in value else (value,value)
    return (*cellpos(a),*cellpos(b))
def within(pos, bounds):
    return bounds[0]<=pos[0]<=bounds[2] and bounds[1]<=pos[1]<=bounds[3]
for index,case in enumerate(cases):
    source=root/(case['input']+'.xlsx')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==case['sourceSha256']
    if case.get('expectedReject'):
        assert engine[index].get('refused')
        results.append(dict(case=index,pages=0,refused=True,passed=True))
        continue
    expected=set(); forbidden=set()
    with zipfile.ZipFile(source) as package:
        book=ET.fromstring(package.read('xl/workbook.xml'))
        for sheet_index, sheet in enumerate(book.findall(f'{{{S}}}sheets/{{{S}}}sheet')):
            tree=ET.fromstring(package.read(f'xl/worksheets/sheet{sheet_index+1}.xml'))
            regions=[]
            for name in book.findall(f'{{{S}}}definedNames/{{{S}}}definedName'):
                if name.get('name')=='_xlnm.Print_Area' and name.get('localSheetId')==str(sheet_index):
                    regions=[rectangle(m) for m in re.findall(r'\$?[A-Z]+\$?\d+(?::\$?[A-Z]+\$?\d+)?',name.text or '')]
            hidden_rows={int(r.get('r')) for r in tree.findall(f'{{{S}}}sheetData/{{{S}}}row') if r.get('hidden')=='1'}
            hidden_cols={i for c in tree.findall(f'{{{S}}}cols/{{{S}}}col') if c.get('hidden')=='1' for i in range(int(c.get('min')),int(c.get('max'))+1)}
            merges=[rectangle(m.get('ref')) for m in tree.findall(f'{{{S}}}mergeCells/{{{S}}}mergeCell')]
            for cell in tree.iter(f'{{{S}}}c'):
                text=''.join(cell.itertext())
                match=re.fullmatch(r'(?:Report|Other|Hidden)-R\d+-C\d+',text)
                if not match: continue
                pos=cellpos(cell.get('r'))
                included=sheet_index in case['sheets'] and sheet.get('state','visible')=='visible' and pos[0] not in hidden_cols and pos[1] not in hidden_rows and (not regions or any(within(pos,b) for b in regions)) and not any(within(pos,b) and pos!=(b[0],b[1]) for b in merges)
                (expected if included else forbidden).add(text)
    doc=pymupdf.open(root/f'output-{index}.pdf')
    text='\n'.join(re.sub(r'[ \t]+','',page.get_text()) for page in doc)
    actual=set(re.findall(r'(?:Report|Other|Hidden)-R\d+-C\d+',text))
    missing=sorted(expected-actual); leaked=sorted(forbidden & actual)
    numeric={14:'3',15:'1,234.56',16:'12.50%',17:'12/9/2025',18:'0'}
    number_ok=index not in numeric or numeric[index] in text
    if case.get('nativeExcel'):
        number_ok = all(value in text for value in ['ITEM-A', 'ITEM-B', 'TOTAL', '77.5']) and all(value not in text for value in ['HIDDEN-NATIVE', 'UNSELECTED-NATIVE'])
    reference=root/f'excel-reference-{index}.pdf'
    ref=pymupdf.open(reference) if reference.exists() else None
    results.append(dict(case=index,pages=len(doc),expectedMarkers=len(expected),actualMarkers=len(actual),missing=missing[:20],leaked=leaked[:20],numericPassed=number_ok,excelPages=len(ref) if ref else None,passed=not missing and not leaked and number_ok))
    doc.close()
    if ref:ref.close()
(root/'independent-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'documents':len(results),'pages':sum(x['pages'] for x in results),'passed':sum(x['passed'] for x in results),'failures':[x for x in results if not x['passed']]},indent=2))
# Representative pages, including long width-fit and deliberately tiny one-page export.
tiles=[]
for i in [0,4,5,6,7,8,12,14,15,16,17,18]:
    doc=pymupdf.open(root/f'output-{i}.pdf')
    pix=doc[0].get_pixmap(matrix=pymupdf.Matrix(0.65,0.65),alpha=False)
    img=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
    tile=Image.new('RGB',(430,610),'#e2e8f0'); tile.paste(img,(10,30)); ImageDraw.Draw(tile).text((10,8),f'Case {i}, {len(doc)} pages',fill='black');tiles.append(tile)
    doc.close()
collage=Image.new('RGB',(430*4,610*3),'white')
for i,img in enumerate(tiles):collage.paste(img,((i%4)*430,(i//4)*610))
collage.save(root/'review.png')
if any(not x['passed'] for x in results):sys.exit(1)
