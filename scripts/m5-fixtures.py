"""Public synthetic fixtures only; never reads user samples."""
import sys,json,hashlib,io
from pathlib import Path
sys.path.insert(0,str(Path('.local-python').resolve()))
import pymupdf as fitz
from PIL import Image,ImageDraw
from fontTools.ttLib import TTFont

out=Path('tests/fixtures/m5');out.mkdir(parents=True,exist_ok=True)
fonts={}
for family,file in [('MaShanZheng','MaShanZheng-Regular.ttf'),('Kalam','Kalam-Regular.ttf'),('Caveat','Caveat.ttf')]:
    cmap=TTFont('public/sign-fonts/'+file).getBestCmap(); ranges=[]
    for n in sorted(cmap):
        if ranges and n==ranges[-1][1]+1:ranges[-1][1]=n
        else:ranges.append([n,n])
    fonts[family]=ranges
Path('src/sign/font-coverage.json').write_text(json.dumps(fonts),encoding='utf-8')
sig=Image.new('RGBA',(240,80));d=ImageDraw.Draw(sig);d.line([(10,60),(50,15),(70,65),(140,25),(200,45),(230,20)],fill=(20,60,140,255),width=4);sig.save(out/'signature.png')
scan=Image.new('RGB',(800,1100),'white');d=ImageDraw.Draw(scan)
d.text((60,80),'SYNTHETIC SCANNED DOCUMENT',fill='black')
for y in range(160,900,30):d.line([(60,y),(650,y)],fill='gray',width=2)
scanbuf=io.BytesIO();scan.save(scanbuf,format='JPEG')
names=['normal-a4','mixed-page-size','landscape','100-pages','scanned','form','chinese','japanese','image-heavy','encrypted','corrupted','large-50mb','zero-pages','200-pages','100mb','unusual-page-sizes']
manifest=[]
for name in names:
    doc=fitz.open()
    count=100 if name=='100-pages' else 200 if name=='200-pages' else 3 if name in ['mixed-page-size','unusual-page-sizes'] else 2
    for i in range(count):
        size=[(300,500),(842,595),(400,1000)][i%3] if name in ['mixed-page-size','unusual-page-sizes'] else (842,595) if name=='landscape' else (595,842)
        p=doc.new_page(width=size[0],height=size[1]);p.insert_text((35,50),f'SYNTHETIC {name} / PAGE {i+1}',fontsize=12)
        if name=='chinese':p.insert_text((35,100),'中文测试文件，原文应保留。',fontname='china-s',fontsize=18)
        if name=='japanese':p.insert_text((35,100),'日本語のテスト文書です。',fontname='japan',fontsize=18)
        if name in ['scanned','image-heavy']:
            p.insert_image(fitz.Rect(20,80,size[0]-20,size[1]-30),stream=scanbuf.getvalue())
        if name=='form':
            w=fitz.Widget();w.field_name='Example'+str(i);w.field_type=fitz.PDF_WIDGET_TYPE_TEXT;w.field_value='SYNTHETIC';w.rect=fitz.Rect(35,100,230,140);p.add_widget(w)
    raw=doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='synthetic-owner',user_pw='test') if name=='encrypted' else doc.tobytes()
    if name=='corrupted':raw=b'%PDF-1.7\ninvalid object\n%%EOF'
    if name in ['large-50mb','100mb']:raw+=b' '*( (50 if name=='large-50mb' else 100)*1024*1024-len(raw))
    if name=='zero-pages':
        # A genuine empty page tree, not a zero-byte file.
        raw= b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
    path=out/(name+'.pdf');path.write_bytes(raw)
    manifest.append({'name':path.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'expected':'reject' if name in ['encrypted','corrupted','large-50mb','zero-pages','100mb'] else 'inspect'})
(out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Created',len(manifest),'synthetic PDFs and signature; font coverage generated.')

