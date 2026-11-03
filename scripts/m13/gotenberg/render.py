"""Render first-cycle PDFs. Repeated cycles have independent glyph-layout checks."""
import json
import subprocess
from pathlib import Path
from PIL import Image,ImageDraw

root=Path('.research/m13/gotenberg')
inventory=[]
for variant in ['default-fonts','noto-fonts']:
    directory=root/variant
    results=json.loads((directory/'results.json').read_text())
    pages=[]
    rendered=directory/'rendered'
    rendered.mkdir(exist_ok=True)
    for row in results['runs']:
        if row['cycle']!=1 or 'file' not in row:continue
        prefix=rendered/Path(row['file']).stem
        subprocess.run(['pdftoppm','-r','100','-png',str(directory/row['file']),str(prefix)],check=True,capture_output=True)
        images=sorted(rendered.glob(prefix.name+'-*.png'))
        for p in images:
            pages.append(p)
            inventory.append({'variant':variant,'document':row['name'],'pageImage':str(p.relative_to(root))})
    for index in range(0,len(pages),9):
        sheet=Image.new('RGB',(1500,2160),'#cbd1d8')
        for offset,path in enumerate(pages[index:index+9]):
            im=Image.open(path).convert('RGB');im.thumbnail((470,665))
            x=(offset%3)*500+(500-im.width)//2;y=(offset//3)*720+12
            sheet.paste(im,(x,y))
            label=path.stem.replace('1-extended-','').replace('1-original-','')
            ImageDraw.Draw(sheet).text(((offset%3)*500+10,(offset//3)*720+686),label,fill='black')
        sheet.save(rendered/f'overview-{index//9+1}.png')
    print(variant,'rendered pages',len(pages),flush=True)
(root/'render-inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf8')
