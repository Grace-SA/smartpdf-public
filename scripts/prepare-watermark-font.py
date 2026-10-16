"""Build the local, renamed regular font from the pinned OFL source.

Requires fontTools. Four-byte glyph padding is deliberate: fontkit's short
loca subset encoder requires even source glyph lengths. Without it, valid
source fonts can produce corrupt, invisible embedded glyphs.
"""
from pathlib import Path
import hashlib
import json
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

source = Path("vendor-fonts/NotoSansSC-variable.ttf")
font = TTFont(source, recalcTimestamp=False)
font = instantiateVariableFont(font, {"wght": 400}, inplace=True)
names = {1: "Smart PDF Sans", 2: "Regular", 4: "Smart PDF Sans Regular",
         6: "SmartPDFSans-Regular", 16: "Smart PDF Sans", 17: "Regular"}
for record in font["name"].names:
    if record.nameID in names:
        record.string = names[record.nameID].encode(record.getEncoding())
font["glyf"].padding = 4
target = Path("public/watermark-fonts/SmartPDFSans-Regular.ttf")
font.save(target)
check = TTFont(target)
assert all(offset % 4 == 0 for offset in check["loca"].locations)
Path("docs/evidence/m10-research/font-derivative.json").write_text(json.dumps({
    "weight": 400, "family": "Smart PDF Sans", "source": "Noto Sans SC variable",
    "bytes": target.stat().st_size,
    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    "cmapSize": len(check.getBestCmap()), "glyphPadding": 4,
}, indent=2), encoding="utf-8")
