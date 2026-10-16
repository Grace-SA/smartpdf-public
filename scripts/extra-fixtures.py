"""Synthetic fixtures only; no user documents are read."""
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from PIL import Image, ImageDraw
import hashlib, json

root = Path('tests/fixtures')
for name, password in [('password-protected', 'synthetic-test-only'), ('owner-encrypted', '')]:
    writer = PdfWriter(clone_from=root / 'plain.pdf')
    writer.encrypt(password, owner_password='synthetic-owner-only', algorithm='AES-256')
    with (root / f'{name}.pdf').open('wb') as stream:
        writer.write(stream)
# A raster-only PDF exercises image decoding independently of the text fixtures.
image = Image.new('RGB', (1200, 1600), 'white')
draw = ImageDraw.Draw(image)
draw.rectangle((80, 80, 1120, 1520), outline='#245740', width=6)
draw.text((150, 200), 'SYNTHETIC SCAN / SmartWorks PDF', fill='black', font_size=42)
image.save(root / 'scan.pdf', 'PDF', resolution=144)
# A 10-page, 5 MiB-size-class synthetic load baseline; padding is an unreferenced stream.
writer = PdfWriter()
reader = PdfReader(root / 'plain.pdf')
for i in range(10): writer.add_page(reader.pages[i % 2])
padding = DecodedStreamObject(); padding.set_data(b'0' * (5 * 1024 * 1024))
writer._add_object(padding)
with (root / 'benchmark-10p-5mib.pdf').open('wb') as stream: writer.write(stream)
manifest = []
for file in sorted(root.glob('*.pdf')):
    manifest.append({'path': file.as_posix(), 'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'origin': 'synthetic; not real user material'})
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
