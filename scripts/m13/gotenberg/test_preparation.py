"""Preparation checks only. These do not exercise Gotenberg or claim conversion quality."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import zipfile
import xml.etree.ElementTree as ET

SPEC=importlib.util.spec_from_file_location('m13_gotenberg_run',Path(__file__).with_name('run.py'))
client=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(client)

class PreparationTests(unittest.TestCase):
    def test_fixed_original_six_remain_intact(self):
        directory=Path('.research/m13/fixtures')
        rows=json.loads((directory/'manifest.json').read_text(encoding='utf8'))
        self.assertEqual(len(rows),6)
        for item in rows:
            self.assertEqual(hashlib.sha256((directory/(item['name']+'.docx')).read_bytes()).hexdigest(),item['sha256'])

    def test_ten_additive_sources_are_well_formed_and_markers_present_once(self):
        directory=Path('.research/m13/gotenberg/fixtures')
        rows=json.loads((directory/'manifest.json').read_text(encoding='utf8'))
        self.assertEqual(len(rows),10)
        for item in rows:
            path=directory/(item['name']+'.docx')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),item['sha256'])
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                texts=[]
                for name in archive.namelist():
                    if name.startswith('word/') and name.endswith('.xml') and ('document' in name or 'header' in name or 'footer' in name):
                        element=ET.fromstring(archive.read(name))
                        texts.extend(e.text or '' for e in element.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
                text=''.join(texts)
                for marker in item['markers']:self.assertEqual(text.count(marker),1,(item['name'],marker))

    def test_cohort_collector_returns_original_plus_additive_without_replacements(self):
        collected=client.collect()
        self.assertEqual(len(collected),16)
        self.assertEqual(sum(kind=='original' for _,_,kind in collected),6)

    def test_multipart_preserves_zip_bytes(self):
        raw=b'PK\x03\x04synthetic\r\nzip-bytes'
        boundary,body=client.multipart(raw)
        self.assertEqual(body.count(raw),1)
        self.assertIn(b'filename="synthetic.docx"',body)
        self.assertTrue(body.endswith(('--'+boundary+'--\r\n').encode()))

if __name__=='__main__':unittest.main()
