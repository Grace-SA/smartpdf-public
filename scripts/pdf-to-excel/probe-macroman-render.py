"""Local counterexample probe; NOT a production font repair or accuracy test.

Run with the pinned Python runtime. Compare before/after PDFium pixel hashes
when a standard ToUnicode map is added to an unembedded MacRoman TrueType font.
The rejected completion stays isolated here; production never imports this file.
"""
import hashlib
import json
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from pdfminer.encodingdb import EncodingDB
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject as D, NameObject as N, DecodedStreamObject
from test_macroman_fonts import font


def probe():
    with tempfile.TemporaryDirectory() as tmp:
        before, after = Path(tmp) / 'before.pdf', Path(tmp) / 'after.pdf'
        writer = PdfWriter(); page = writer.add_blank_page(width=300, height=200)
        page[N('/Resources')] = D({N('/Font'): D({N('/F1'): font()})})
        content = DecodedStreamObject()
        content.set_data(b'BT /F1 20 Tf 30 120 Td (A\\336 B\\337 \\200 7.25) Tj ET')
        page[N('/Contents')] = content
        writer.write(before)
        reader = PdfReader(before)
        lines = ['/CIDInit /ProcSet findresource begin', '12 dict begin begincmap',
                 '/CMapType 2 def', '/CMapName /ExperimentalMacRoman def',
                 '1 begincodespacerange', '<00> <FF>', 'endcodespacerange']
        entries = sorted(EncodingDB.get_encoding('MacRomanEncoding').items())
        for start in range(0, len(entries), 100):
            chunk = entries[start:start+100]
            lines += [f'{len(chunk)} beginbfchar']
            lines += [f'<{k:02X}> <{v.encode("utf-16-be").hex()}>' for k, v in chunk]
            lines += ['endbfchar']
        lines += ['endcmap CMapName currentdict /CMap defineresource pop', 'end end']
        cmap = DecodedStreamObject(); cmap.set_data('\n'.join(lines).encode())
        reader.pages[0]['/Resources']['/Font']['/F1'][N('/ToUnicode')] = cmap
        PdfWriter(clone_from=reader).write(after)
        hashes = []
        for path in (before, after):
            doc = pdfium.PdfDocument(path); page = doc[0]; bitmap = page.render(scale=2)
            hashes.append(hashlib.sha256(bitmap.to_pil().tobytes()).hexdigest())
            bitmap.close(); page.close(); doc.close()
        return dict(engine='PDFium', scale=2, beforeSha256=hashes[0],
                    afterSha256=hashes[1], identicalPixels=hashes[0] == hashes[1])


if __name__ == '__main__':
    print(json.dumps(probe(), sort_keys=True))
