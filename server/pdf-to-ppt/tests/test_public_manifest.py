"""Expand public evidence without silently replacing the fixed regression pages."""
import json
from pathlib import Path


def test_existing_public_inputs_and_page_identities_are_preserved():
 data=json.loads((Path(__file__).parents[1]/'tools'/'public-native-manifest.json').read_text())
 expected={
  'dummy':('3df79d34abbca99308e79cb94461c1893582604d68329a41fd4bec1885e6adb4',[1]),
  'fw9':('2d420cbb4123dcf1fb82595b2359cfbb5d81f00b9df9d359fcc7af361d093f53',[1,2]),
  'attention':('bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697',[1,3,5]),
 }
 assert data['version']==2
 assert [d['name'] for d in data['documents']]==list(expected)
 for d in data['documents']:
  digest,pages=expected[d['name']]
  assert d['sha256']==digest and d['pages'][:len(pages)]==pages
  assert len(d['pages'])==len(set(d['pages'])) and all(isinstance(n,int) and n>0 for n in d['pages'])
 assert sum(len(d['pages']) for d in data['documents'])==8
