"""Export only allow-listed synthetic numerical evidence; never copy raw PDF text."""
import json
from pathlib import Path

root = Path('.research/m13')
rows = json.loads((root/'word-reference/comparison.json').read_text(encoding='utf8'))
summary = json.loads((root/'word-reference/comparison-summary.json').read_text(encoding='utf8'))
sources = json.loads((root/'word-reference/source-integrity.json').read_text())
assert len(rows) == len(summary) == len(sources) == 16
assert all(r['expected'] == r['actual'] for r in sources)
manifests = [root/'fixtures/manifest.json', root/'gotenberg/fixtures/manifest.json']
known = {i['name']:i for p in manifests for i in json.loads(p.read_text(encoding='utf8'))}
assert set(r['name'] for r in rows) == set(known)
pages = []
documents = []
for row, brief in zip(rows,summary):
    assert row['name'] == brief['name'] and row['inputSha256'] == known[row['name']]['sha256']
    assert not brief['wordMissingMarkers']
    for variant in ['default-fonts','noto-fonts']:
        assert not brief[variant]['missingMarkers']
        assert not brief[variant]['repeatedMarkerFailures']
    documents.append(dict(name=row['name'],inputSha256=row['inputSha256'],
                          wordPdfSha256=row['word']['sha256'],**{k:v for k,v in brief.items() if k!='name'}))
    for p in row['variants']['noto-fonts']['pageComparison']:
        assert p['wordPresent'] and p['nativePresent']
        assert not p['wordOnlyMarkers'] and not p['nativeOnlyMarkers']
        wp=row['word']['pages'][p['page']-1]
        lp=row['variants']['noto-fonts']['pdf']['pages'][p['page']-1]
        pages.append(dict(name=row['name'],page=p['page'],sharedMarkers=p['sharedMarkers'],
                          maxMarkerBoxDeltaPt=p['maxMarkerBoxDeltaPt'],
                          pageBoxMaxDeltaPt=round(max(abs(wp[k]-lp[k]) for k in ['width','height']),3)))
data=dict(date='2026-10-28',syntheticOnly=True,sourceDocuments=16,sourceHashesUnchanged=True,
          wordVersion='16.0.20430.20182',wordExport='Standard PDF desktop UI',
          wordReferencePages=34,notoComparedPages=len(pages),
          baseAsciiMarkers=sum(sum(m.isascii() for m in i['markers']) for i in known.values()),
          sameFontExperiment=False,wordChineseExtractionReliable=False,
          productAcceptanceCompleted=False,documents=documents,pageComparisons=pages)
target=Path('docs/ux/public-synthetic-only/m13-word-reference-summary.json')
target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
table=['| 样本 | Word 页 | 默认字体页 | 固定 Noto 页 | Noto 标记框最大差异 pt |',
       '| --- | ---: | ---: | ---: | ---: |']
for r in summary:
    table.append(f"| {r['name']} | {r['wordPages']} | {r['default-fonts']['pages']} | {r['noto-fonts']['pages']} | {r['noto-fonts']['maxMarkerBoxDeltaPt']:.3f} |")
table += ['','| 样本 | 页 | 同页匹配标记数 | 标记框最大差异 pt | 页框最大差异 pt |',
          '| --- | ---: | ---: | ---: | ---: |']
for p in pages:
    table.append(f"| {p['name']} | {p['page']} | {p['sharedMarkers']} | {p['maxMarkerBoxDeltaPt']:.3f} | {p['pageBoxMaxDeltaPt']:.3f} |")
(root/'word-reference/report-tables.md').write_text('\n'.join(table)+'\n',encoding='utf8')
print('Exported 16 synthetic documents,',len(pages),'page comparisons; raw text excluded.')
