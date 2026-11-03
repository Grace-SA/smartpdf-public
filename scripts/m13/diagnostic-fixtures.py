"""Additive minimum reproduction inputs; never modify the six frozen sources."""
from pathlib import Path
from docx import Document
from docx.shared import Inches

root=Path('.research/m13/fixtures')
assert (root/'manifest.json').exists(), 'Generate and freeze the original six first'
for case in ['table-only','image-only','header-only','simple-two-pages']:
    output=root/(case+'.docx')
    if output.exists():
        continue
    d=Document()
    d.add_paragraph('DIAGNOSTIC-'+case)
    if case=='table-only':
        table=d.add_table(rows=3,cols=3)
        table.style='Table Grid'
        table.cell(0,0).text='TABLE-DIAGNOSTIC'
    if case=='image-only':
        d.add_picture(str(root/'synthetic.png'),width=Inches(2))
    if case=='header-only':
        d.sections[0].header.paragraphs[0].text='HEADER-DIAGNOSTIC'
        d.sections[0].footer.paragraphs[0].text='FOOTER-DIAGNOSTIC'
    if case=='simple-two-pages':
        d.add_page_break()
        d.add_paragraph('PAGE-TWO')
    d.save(output)
