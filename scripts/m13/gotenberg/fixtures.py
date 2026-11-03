"""Add ten synthetic native-engine probes without modifying earlier fixtures."""
import hashlib
import json
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path('.research/m13/gotenberg')
SOURCE=ROOT/'fixtures'
SOURCE.mkdir(parents=True,exist_ok=True)
if (SOURCE/'manifest.json').exists():
    raise SystemExit('Manifest frozen; do not overwrite this cohort.')
records=[]

def base():
    d=Document()
    s=d.sections[0]
    s.page_width,s.page_height=Inches(8.27),Inches(11.69)
    s.top_margin=s.bottom_margin=s.left_margin=s.right_margin=Inches(0.8)
    normal=d.styles['Normal']
    normal.font.name='Noto Sans SC'
    normal.font.size=Pt(11)
    normal.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Noto Sans SC')
    return d

def row_repeat(row):
    row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))

def save(d,name,markers,**expect):
    path=SOURCE/(name+'.docx')
    d.save(path)
    records.append(dict(name=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        markers=markers,**expect))

d=base()
d.add_heading('中文排版与字体测试',0)
phrases=['中文标点：逗号，句号。引号“测试”与括号（示例）。',
         '中英混排 ABC 123，金额 1,234.56，日期 2026-10-28。',
         '简体中文与繁體中文：转换、轉換、表格、頁碼。']
for i,p in enumerate(phrases):d.add_paragraph(f'CJK-{i:03d} '+p)
save(d,'chinese-punctuation',['CJK-000','CJK-001','CJK-002',*phrases],expectedPages=1)

d=base()
for i,size in enumerate([9,11,14,18,24]):
    p=d.add_paragraph()
    r=p.add_run(f'SIZE-{i:03d} 中文字号与粗体测试');r.font.size=Pt(size);r.bold=i%2==1
save(d,'chinese-sizes',[f'SIZE-{i:03d}' for i in range(5)],expectedPages=1)

d=base();t=d.add_table(rows=6,cols=4);t.style='Table Grid'
t.cell(0,0).merge(t.cell(0,3)).text='MERGE-TITLE 中文合并总表头'
t.cell(1,0).merge(t.cell(2,0)).text='VERTICAL-MERGE 纵向合并'
t.cell(1,1).merge(t.cell(1,2)).text='HORIZONTAL-MERGE 横向合并'
markers=['MERGE-TITLE','VERTICAL-MERGE','HORIZONTAL-MERGE']
for row in range(3,6):
    for col in range(4):
        tag=f'CELL-{row}-{col}';t.cell(row,col).text=tag+' 中文单元格';markers.append(tag)
save(d,'chinese-merged-table',markers,expectedPages=1)

d=base();t=d.add_table(rows=2,cols=2);t.style='Table Grid'
t.cell(0,0).text='OUTER-A';t.cell(0,1).text='OUTER-B'
nested=t.cell(1,0).add_table(rows=3,cols=2);nested.style='Table Grid'
markers=['OUTER-A','OUTER-B','OUTER-C']
t.cell(1,1).text='OUTER-C 中文侧栏'
for row in range(3):
    for col in range(2):
        tag=f'NESTED-{row}-{col}';nested.cell(row,col).text=tag+' 内表';markers.append(tag)
save(d,'nested-table',markers,expectedPages=1)

d=base();t=d.add_table(rows=101,cols=3);t.style='Table Grid';row_repeat(t.rows[0])
for i,text in enumerate(['REPEATED-HEADER 编号','品名','数量']):t.cell(0,i).text=text
markers=[]
for row in range(1,101):
    tag=f'LONGROW-{row:03d}';markers.append(tag)
    for col,text in enumerate([tag,'中文产品名称与数量核对','数量：十二']):t.cell(row,col).text=text
save(d,'chinese-long-table',markers,minPages=2,repeatedHeader='REPEATED-HEADER')

d=base();t=d.add_table(rows=2,cols=2);t.style='Table Grid';row_repeat(t.rows[0])
t.cell(0,0).text='SPLIT-HEADER';t.cell(0,1).text='多段落跨页行'
markers=[]
for col in range(2):
    cell=t.cell(1,col)
    for line in range(45):
        tag=f'SPLIT-{col}-{line:03d}';markers.append(tag)
        p=cell.paragraphs[0] if line==0 else cell.add_paragraph()
        p.text=tag+' 跨页内容必须完整保留'
save(d,'long-row-split',markers,minPages=2,repeatedHeader='SPLIT-HEADER')

d=base();s=d.sections[0]
s.header.paragraphs[0].text='EXPLICIT-HEADER 中文页眉'
s.footer.paragraphs[0].text='EXPLICIT-FOOTER 中文页脚'
for page in range(3):
    if page:d.add_page_break()
    d.add_paragraph(f'EXPLICIT-PAGE-{page+1} 中文分页核验')
save(d,'chinese-explicit-pages',[f'EXPLICIT-PAGE-{i}' for i in range(1,4)],expectedPages=3,
     repeatedHeader='EXPLICIT-HEADER',repeatedFooter='EXPLICIT-FOOTER')

d=base();s=d.sections[0];s.orientation=WD_ORIENT.LANDSCAPE
s.page_width,s.page_height=Inches(11.69),Inches(8.27)
t=d.add_table(rows=12,cols=8);t.style='Table Grid';markers=[]
for row in range(12):
    for col in range(8):
        tag=f'WIDE-{row:02d}-{col}';markers.append(tag);t.cell(row,col).text=tag+' 中文'
save(d,'landscape-wide-table',markers,expectedPages=1,orientations=['landscape'])

d=base();d.sections[0].header.paragraphs[0].text='SECTION-A-HEADER'
d.add_paragraph('SECTION-A-BODY 中文竖版')
s=d.add_section(WD_SECTION_START.NEW_PAGE);s.header.is_linked_to_previous=False
s.header.paragraphs[0].text='SECTION-B-HEADER';s.orientation=WD_ORIENT.LANDSCAPE
s.page_width,s.page_height=Inches(11.69),Inches(8.27)
d.add_paragraph('SECTION-B-BODY 中文横版')
save(d,'separate-section-headers',['SECTION-A-BODY','SECTION-B-BODY','SECTION-A-HEADER','SECTION-B-HEADER'],
     expectedPages=2,orientations=['portrait','landscape'],
     pageMarkers={'1':['SECTION-A-BODY','SECTION-A-HEADER'],'2':['SECTION-B-BODY','SECTION-B-HEADER']})

d=base();markers=[]
for i in range(70):
    tag=f'PARAGRAPH-{i:03d}';markers.append(tag)
    p=d.add_paragraph(tag+' 中文自动分页核对，内容应依次排列，不能裁切或丢失。')
    p.paragraph_format.widow_control=True
    p.paragraph_format.space_after=Pt(8)
save(d,'chinese-auto-pagination',markers,minPages=2)

(SOURCE/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'additionalDocuments':len(records),'frozenManifest':str(SOURCE/'manifest.json')}))
