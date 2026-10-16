"""Synthetic RGB/alpha/EXIF fixtures with linear TRCs, no private images."""
import sys, struct, zlib
from pathlib import Path
sys.path.insert(0, str(Path('node_modules/.cache/heic-fixture-tools').resolve()))
from PIL import Image, ImageDraw, ImageCms
out = Path('tests/fixtures/photos')
profile = bytearray((out/'synthetic-srgb.icc').read_bytes())
for i in range(struct.unpack_from('>I', profile, 128)[0]):
    p = 132 + 12*i
    if bytes(profile[p:p+4]) in (b'rTRC', b'gTRC', b'bTRC'):
        offset = struct.unpack_from('>I', profile, p+4)[0]
        profile[offset:offset+4] = b'para'
        struct.pack_into('>H', profile, offset+8, 0)
        struct.pack_into('>i', profile, offset+12, 65536)
profile = bytes(profile)
im = Image.new('RGB',(120,80),(128,128,128))
d = ImageDraw.Draw(im)
d.rectangle((0,0,59,39), fill=(120,60,30))
d.rectangle((60,0,119,39), fill=(30,120,60))
exif = Image.Exif(); exif[274] = 6
im.save(out/'color-linear.jpg',quality=98,icc_profile=profile,exif=exif.tobytes())
alpha = im.convert('RGBA'); alpha.putalpha(180)
alpha.save(out/'color-linear.png',icc_profile=profile)
im.save(out/'color-gamma.png')
raw = (out/'color-gamma.png').read_bytes()
def chunk(name, data):
    return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data))
(out/'color-gamma.png').write_bytes(raw[:33]+chunk(b'gAMA',struct.pack('>I',100000))+raw[33:])
print('Created synthetic linear ICC JPEG, transparent PNG, gamma PNG.')
