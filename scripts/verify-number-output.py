"""Read only synthetic number-test outputs; verify with an independent renderer."""
from pathlib import Path
import json
import math
import pymupdf
from PIL import Image, ImageChops, ImageDraw

root = Path('docs/evidence/m9-output')
checks = []
for sidecar in sorted(root.glob('*.json')):
    case = json.loads(sidecar.read_text(encoding='utf-8'))
    original = pymupdf.open(case['source'])
    output = pymupdf.open(sidecar.with_suffix('.pdf'))
    assert len(original) == len(output)
    for index, stamp in enumerate(case['plan']['stamps']):
        before = original[index].get_pixmap(alpha=False)
        after = output[index].get_pixmap(alpha=False)
        assert (before.width, before.height) == (after.width, after.height)
        a = Image.frombytes('RGB', (before.width,before.height), before.samples)
        b = Image.frombytes('RGB', (after.width,after.height), after.samples)
        difference = ImageChops.difference(a,b)
        box = difference.getbbox()
        if stamp is None:
            assert box is None, (sidecar.name,index,'unselected page changed')
        else:
            assert stamp['text'] in output[index].get_text(), (sidecar.name,index,'number text missing')
            assert box is not None, (sidecar.name,index,'invisible number')
            x,y,w,h = (stamp[key] for key in ['x','y','width','height'])
            permitted=(math.floor(x)-2,math.floor(y)-2,math.ceil(x+w)+2,math.ceil(y+h)+2)
            assert box[0]>=permitted[0] and box[1]>=permitted[1] and box[2]<=permitted[2] and box[3]<=permitted[3],(sidecar.name,index,box,permitted)
            ImageDraw.Draw(difference).rectangle(permitted,fill=(0,0,0))
            assert difference.getbbox() is None,(sidecar.name,index,'pixels outside number changed')
        checks.append({'case':sidecar.stem,'page':index+1,'textVerified':stamp is not None,'outsidePlannedAreaUnchanged':True})
    original.close()
    output.close()
report={'renderer':'PyMuPDF','documents':len(list(root.glob('*.json'))),'pages':len(checks),'passed':len(checks),'checks':checks}
Path('docs/evidence/m9-independent-output.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in report.items() if key!='checks'}))
