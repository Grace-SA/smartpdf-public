"""Independent MuPDF checks of approved synthetic M11 outputs; no private inputs."""
from pathlib import Path
import hashlib
import json
import pymupdf as fitz

root = Path('.research/m11')
expected = {'normal-a4','mixed-page-size','landscape','100-pages','scanned',
            'form','chinese','japanese','image-heavy','200-pages','unusual-page-sizes'}
folder = root / 'regression-outputs'
assert {p.stem for p in folder.glob('*.pdf')} == expected, 'Incomplete synthetic output set'
manifest = {r['name']: r for r in json.loads(Path('tests/fixtures/m5/manifest.json').read_text())}

def links(page):
    return [{k:str(v) for k,v in link.items() if k not in ('xref','id')} for link in page.get_links()]

def verify(source_path, output_path, password):
    original = source_path.read_bytes()
    with fitz.open(source_path) as source, fitz.open(output_path) as output:
        assert output.needs_pass and output.is_encrypted, (output_path.stem, 'not encrypted')
        assert not output.authenticate('') and not output.authenticate('wrong-synthetic'), 'Missing/wrong password opened output'
        assert output.authenticate(password), (output_path.stem, 'correct password rejected')
        assert output.metadata['encryption'] == 'Standard V5 R6 256-bit AES', 'Unexpected cipher or revision'
        assert len(source) == len(output), 'Page count changed'
        assert source.get_toc() == output.get_toc(), 'Bookmarks changed'
        assert source.get_page_labels() == output.get_page_labels(), 'Page labels changed'
        assert sorted(str(v) for v in source.get_ocgs().values()) == sorted(str(v) for v in output.get_ocgs().values()), 'Layers changed'
        assert source.embfile_names() == output.embfile_names(), 'Attachments changed'
        for index, (before, after) in enumerate(zip(source, output)):
            assert before.rect == after.rect and before.rotation == after.rotation, (output_path.stem, index, 'geometry')
            assert before.get_text() == after.get_text(), (output_path.stem, index, 'text')
            assert before.get_pixmap(matrix=fitz.Matrix(.5,.5)).samples == after.get_pixmap(matrix=fitz.Matrix(.5,.5)).samples, (output_path.stem, index, 'pixels')
            assert links(before) == links(after), (output_path.stem, index, 'links')
            assert [(w.field_name,w.field_value,w.field_type) for w in before.widgets() or []] == [(w.field_name,w.field_value,w.field_type) for w in after.widgets() or []], (output_path.stem, index, 'forms')
        pages = len(source)
    assert source_path.read_bytes() == original, 'Source modified'
    return pages

rows = []
for name in sorted(expected):
    source = Path('tests/fixtures/m5') / (name + '.pdf')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest[source.name]['sha256'], 'Frozen source changed'
    rows.append({'case':name,'pages':verify(source, folder/(name+'.pdf'), 'Synthetic-M11-Only!')})
variants = {'ascii':'Synthetic-M11-Only!', 'unicode':'中文密码测试-123', 'spaces':'  pass phrase  ',
            'option':'--option-password', 'emoji':'emoji-😀-123', 'combining':'sample-e\u0301-123', 'max':'x'*127}
assert {p.stem for p in (root/'outputs').glob('*.pdf')} == set(variants), 'Incomplete password variants'
for name, password in variants.items():
    rows.append({'case':'password-'+name,'pages':verify(Path('docs/ux/public-synthetic-only/demo-a.pdf'), root/'outputs'/(name+'.pdf'), password)})
rich = {'navigation-a','layer-on','final-tags'}
assert {p.stem for p in (root/'rich-outputs').glob('*.pdf')} == rich, 'Incomplete rich structures'
for name in sorted(rich):
    rows.append({'case':name,'pages':verify(Path('tests/fixtures/combine')/(name+'.pdf'), root/'rich-outputs'/(name+'.pdf'), 'Synthetic-M11-Only!')})
record = {'engine':'MuPDF','documents':len(rows),'pages':sum(r['pages'] for r in rows),'passed':len(rows),'checks':rows}
Path('docs/evidence').mkdir(parents=True, exist_ok=True)
Path('docs/evidence/m11-independent.json').write_text(json.dumps(record, indent=2), encoding='utf8')
print(json.dumps({k:v for k,v in record.items() if k!='checks'}))
