from pathlib import Path
from PIL import Image, ImageDraw

root=Path('tests/fixtures/watermark');root.mkdir(exist_ok=True)
image=Image.new('RGBA',(120,80),(0,0,0,0))
draw=ImageDraw.Draw(image);draw.rectangle((15,15,105,65),fill=(20,110,210,255));draw.rectangle((45,25,75,55),fill=(255,255,255,255))
image.save(root/'logo.png')
Image.new('RGBA',(40,40),(255,255,255,0)).save(root/'transparent.png')
Image.new('RGB',(2100,2100),(220,70,20)).save(root/'oversized.png')
photo=Image.new('RGB',(100,60),(30,180,70));ImageDraw.Draw(photo).rectangle((0,0,35,60),fill=(210,40,30))
exif=Image.Exif();exif[274]=6;photo.save(root/'orientation.jpg',exif=exif,quality=95)
(root/'corrupted.png').write_bytes(b'not an image')
print('Five public synthetic watermark image fixtures created')
