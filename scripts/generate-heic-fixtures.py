"""Create original synthetic HEIC fixtures locally; no private photos are used."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path('node_modules/.cache/heic-fixture-tools').resolve()))
from PIL import Image, ImageDraw, ImageCms
import pillow_heif
pillow_heif.register_heif_opener()
out = Path('tests/fixtures/photos')
image = Image.new('RGB', (320, 240), 'white')
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, 159, 119), fill='red')
draw.rectangle((160, 0, 319, 119), fill='green')
draw.rectangle((0, 120, 159, 239), fill='blue')
draw.text((180, 160), 'SmartWorks 20', fill='black')
image.save(out / 'synthetic.heic', quality=95)
image.save(out / 'synthetic-control.png')
profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
(out / 'synthetic-srgb.icc').write_bytes(profile)
image.save(out / 'synthetic-icc.heic', quality=95, icc_profile=profile)
exif = Image.Exif()
exif[274] = 6
image.save(out / 'synthetic-rotated.heic', quality=95, exif=exif.tobytes())
image.save(out / 'synthetic-multi.heic', save_all=True, append_images=[image.transpose(Image.Transpose.ROTATE_90)], quality=95)
large = image.resize((4032, 3024))
large.save(out / 'synthetic-12mp.heic', quality=90)
print('Created original 1-photo, 2-photo and 12MP HEIC fixtures.')
