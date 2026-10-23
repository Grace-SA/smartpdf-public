"""Independently validate synthetic outputs. Never read a private corpus here."""
from pathlib import Path
import hashlib
import json
import pymupdf as fitz

folder=Path('.test-output/unlock')
rich={'navigation':'navigation-a','layers':'layer-on','tags':'final-tags','attachments':'final-attachment'}
expected={f'reg-{name}' for name in ('normal-a4','mixed-page-size','landscape','100-pages','200-pages','scanned','form','chinese','japanese','image-heavy')}
expected.update(f'{name}-{role}' for name in ('rc4-40','rc4-128','aes-128','aes-256','r5','unicode','legacy-encoding','special','empty-user') for role in ('user','owner'))
expected.update(rich)
expected.add('standard')
assert {f.stem for f in folder.glob('*.pdf')}==expected,'Incomplete or unexpected synthetic output set'
checks=[]
def links(page):
    return [{k:str(v) for k,v in item.items() if k not in ('xref','id')} for item in page.get_links()]
for name in sorted(expected):
    original=Path('tests/fixtures/m5')/(name[4:]+'.pdf') if name.startswith('reg-') else Path('tests/fixtures/combine')/(rich[name]+'.pdf') if name in rich else Path('tests/fixtures/m5/normal-a4.pdf')
    with fitz.open(original) as source,fitz.open(folder/(name+'.pdf')) as output:
        assert not output.is_encrypted and not output.needs_pass,(name,'encryption')
        assert len(source)==len(output),(name,'pages')
        assert source.get_toc()==output.get_toc(),(name,'bookmarks')
        assert source.get_page_labels()==output.get_page_labels(),(name,'page labels')
        assert source.embfile_names()==output.embfile_names(),(name,'attachments')
        for item in source.embfile_names():
            assert hashlib.sha256(source.embfile_get(item)).digest()==hashlib.sha256(output.embfile_get(item)).digest(),(name,'attachment data')
        assert sorted(str(v) for v in source.get_ocgs().values())==sorted(str(v) for v in output.get_ocgs().values()),(name,'layers')
        for i,(before,after) in enumerate(zip(source,output)):
            assert before.rect==after.rect and before.rotation==after.rotation,(name,i,'geometry')
            assert before.get_text()==after.get_text(),(name,i,'text')
            assert before.get_pixmap().samples==after.get_pixmap().samples,(name,i,'pixels')
            assert links(before)==links(after),(name,i,'links')
            assert [(w.field_name,w.field_value,w.field_type) for w in before.widgets() or []]==[(w.field_name,w.field_value,w.field_type) for w in after.widgets() or []],(name,i,'forms')
        checks.append({'case':name,'pages':len(output),'passed':True})
record={'documents':len(checks),'pages':sum(c['pages'] for c in checks),'passed':len(checks),'checks':checks}
Path('docs/evidence').mkdir(parents=True,exist_ok=True)
Path('docs/evidence/m12-independent.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in record.items() if k!='checks'}))
