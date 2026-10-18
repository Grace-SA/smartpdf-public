from pathlib import Path
import hashlib
import json
from fontTools.ttLib import TTFont
from fontTools import subset

source = Path('public/watermark-fonts/SmartPDFSans-Regular.ttf')
assert hashlib.sha256(source.read_bytes()).hexdigest() == '6b746ab1c30e6f3cb634af270268368f5348366d0a9c76b5a0b9c16c591b8acb'
font = TTFont(source, recalcTimestamp=False)
options = subset.Options()
options.layout_features = []
options.recalc_timestamp = False
subsetter = subset.Subsetter(options=options)
subsetter.populate(unicodes=range(32, 127))
subsetter.subset(font)
names = {1:'Smart PDF Number Sans',2:'Regular',4:'Smart PDF Number Sans Regular',6:'SmartPDFNumberSans-Regular',16:'Smart PDF Number Sans',17:'Regular'}
for record in font['name'].names:
    if record.nameID in names:
        record.string = names[record.nameID].encode(record.getEncoding())
font['glyf'].padding = 4
target = Path('public/number-fonts/SmartPDFNumberSans-Regular.ttf')
target.parent.mkdir(parents=True, exist_ok=True)
font.save(target)
check = TTFont(target, recalcTimestamp=False)
assert all(offset % 4 == 0 for offset in check['loca'].locations)
assert all(code in check.getBestCmap() for code in range(32,127))
Path('docs/evidence').mkdir(parents=True, exist_ok=True)
Path('docs/evidence/m9-font.json').write_text(json.dumps({'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size,'codepoints':'ASCII 32-126','license':'SIL OFL 1.1','glyphPadding':4},indent=2),encoding='utf-8')
