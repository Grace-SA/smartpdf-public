"""Independent public fixture: a wide table with a picture and no saved print setup."""
import hashlib
import json
from pathlib import Path
import sys
import xlsxwriter
from PIL import Image, ImageDraw

root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
picture = Image.new('RGB', (120, 45), 'white')
draw = ImageDraw.Draw(picture)
draw.rectangle((5, 5, 50, 40), fill='#e02020')
draw.rectangle((65, 5, 115, 40), fill='#1050df')
picture.save(root / 'public-picture.png')
target = root / 'picture-table.xlsx'
book = xlsxwriter.Workbook(target)
book.set_properties({'author':'Smart PDF public synthetic fixture', 'created':__import__('datetime').datetime(2026,1,1)})
sheet = book.add_worksheet('Public table')
sheet.set_column('A:F', 18); sheet.set_default_row(36)
expected = []
for row in range(10):
    for column in range(6):
        text = f'PUBLIC-{row+1:02}-{column+1:02}'
        if row == 3 and column == 1: continue
        sheet.write(row, column, text); expected.append(text)
sheet.insert_image('B4', str(root/'public-picture.png'))
book.close()
(root/'cases.json').write_text(json.dumps([{'input':'picture-table','sheets':[0],'scale':'auto',
    'sourceSha256':hashlib.sha256(target.read_bytes()).hexdigest(),'expected':expected,'forbidden':[],
    'repeatHeader':False,'singlePanelColumns':0,'minMedianFont':8,'maxPages':1}],indent=2))
