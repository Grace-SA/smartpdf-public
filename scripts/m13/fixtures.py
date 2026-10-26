"""Synthetic DOCX research fixtures only. No user inputs or system fonts."""
from pathlib import Path
import json, hashlib
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw

root = Path('.research/m13/fixtures')
root.mkdir(parents=True, exist_ok=True)
if (root / 'manifest.json').exists():
    raise SystemExit('Frozen fixture manifest already exists; preserve it and use a new research directory for a new cohort.')
manifest = []

def base():
    d = Document()
    s = d.sections[0]
    s.page_width, s.page_height = Inches(8.27), Inches(11.69)
    s.top_margin = s.bottom_margin = s.left_margin = s.right_margin = Inches(1)
    d.styles['Normal'].font.name = 'Liberation Sans'
    d.styles['Normal'].font.size = Pt(11)
    return d

def save(d, name, markers, pages=None):
    p = root / (name + '.docx')
    d.save(p)
    manifest.append(dict(name=name, sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                         markers=markers, expectedPages=pages))

d = base()
d.add_heading('Synthetic conversion sample', 0)
d.sections[0].header.paragraphs[0].text = 'HEADER-M13'
d.sections[0].footer.paragraphs[0].text = 'FOOTER-M13'
d.add_paragraph('FIRST-PAGE-MARKER')
t = d.add_table(rows=3, cols=3)
t.style = 'Table Grid'
for r in range(3):
    for c in range(3): t.cell(r,c).text = f'CELL-{r}-{c}'
t.cell(0,0).merge(t.cell(0,1)).text = 'MERGED-CELL'
im=Image.new('RGB',(320,120),'#dce9f8'); ImageDraw.Draw(im).rectangle((10,10,310,110),outline='#205090',width=6)
im.save(root/'synthetic.png')
d.add_picture(str(root/'synthetic.png'),width=Inches(2))
d.add_page_break(); d.add_paragraph('SECOND-PAGE-MARKER')
save(d,'explicit-pages-table-image',['FIRST-PAGE-MARKER','SECOND-PAGE-MARKER','MERGED-CELL','CELL-2-2','HEADER-M13','FOOTER-M13'],2)

d=base()
markers=[]
for i in range(120):
    label=f'FLOW-{i:03d}'
    markers.append(label)
    p=d.add_paragraph(label+' Ordinary text must continue to later pages without being clipped or dropped.')
    p.paragraph_format.space_after=Pt(8)
save(d,'automatic-pagination',markers)

d=base(); d.add_paragraph('PORTRAIT-SECTION')
s=d.add_section(WD_SECTION_START.NEW_PAGE); s.orientation=WD_ORIENT.LANDSCAPE
s.page_width,s.page_height=Inches(11.69), Inches(8.27)
d.add_paragraph('LANDSCAPE-SECTION')
save(d,'mixed-orientation',['PORTRAIT-SECTION','LANDSCAPE-SECTION'],2)

d=base()
p=d.add_paragraph(); r=p.add_run('中文转换测试：段落、表格与分页。日本語の変換テスト。')
r.font.name='Noto Sans SC'; r._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Noto Sans SC')
d.add_paragraph('CJK-END')
save(d,'cjk',['中文转换测试','日本語','CJK-END'],1)

d=base(); r=d.add_paragraph().add_run('MISSING-FONT-MARKER'); r.font.name='SyntheticNonexistentFontM13'
save(d,'missing-font',['MISSING-FONT-MARKER'],1)

d=base(); d.add_paragraph('LONG-TABLE-START')
t=d.add_table(rows=81,cols=2); t.style='Table Grid'; t.cell(0,0).text='TABLE-HEADER'
repeat=OxmlElement('w:tblHeader'); t.rows[0]._tr.get_or_add_trPr().append(repeat)
for i in range(1,81):
    t.cell(i,0).text=f'ROW-{i:03d}'; t.cell(i,1).text='Multi-page table content stays in its own cell.'
save(d,'long-table',[f'ROW-{i:03d}' for i in range(1,81)])

(root/'empty.docx').write_bytes(b'')
(root/'corrupt.docx').write_bytes(b'PK\x03\x04truncated')
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'fixtures':len(manifest),'directory':str(root)}))
