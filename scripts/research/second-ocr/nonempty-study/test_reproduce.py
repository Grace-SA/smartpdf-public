import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('nonempty_reproduce', HERE/'reproduce.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class ReproductionTests(unittest.TestCase):
    def test_source_hash_rejects_before_runtime_or_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'wrong.pdf'; p.write_bytes(b'%PDF-not-the-public-source')
            with patch.object(m,'check_runtime',side_effect=AssertionError('must not run')):
                with self.assertRaisesRegex(ValueError,'Source hash mismatch'):
                    m.run(p,Path(directory)/'out.json')
            self.assertFalse((Path(directory)/'out.json').exists())

    def test_runtime_and_model_mismatch_decline(self):
        locked=json.loads((HERE/'inputs.json').read_text())
        with patch.object(m.importlib.metadata,'version',return_value='mismatch'):
            with self.assertRaisesRegex(ValueError,'Runtime version mismatch'):
                m.check_runtime(locked)
        bad=copy.deepcopy(locked)
        for key in bad['primaryModels']:bad['primaryModels'][key]='0'*64
        with self.assertRaisesRegex(ValueError,'Primary model hash mismatch'):
            m.check_runtime(bad)
        m.check_runtime(locked)

    def test_variants_bounded_and_never_mutate_input(self):
        page=np.arange(100*120*3,dtype=np.uint32).reshape(100,120,3).astype(np.uint8)
        original=page.copy()
        fields=[{'name':'Delaware','box':[20,20,48,45],'manualSource':'90'},
                {'name':'Georgia','box':[30,50,92,78],'manualSource':'58,980'}]
        cases=m.make_cases(page,fields)
        self.assertEqual(len(cases),12);self.assertTrue(np.array_equal(original,page))
        self.assertEqual(sum(expected is not None for _,_,expected in cases),6)
        self.assertTrue(all(im.shape[0]*im.shape[1]<=16384 for _,im,_ in cases))
        self.assertTrue(np.all(cases[-1][1]==255))
        fields[0]['box']=[0,0,28,25]
        with self.assertRaisesRegex(ValueError,'outside fixed page'):m.make_cases(page,fields)

    def test_explicit_research_opt_in_required(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'out.json'
            result=subprocess.run([sys.executable,str(HERE/'reproduce.py'),'--source',str(Path(directory)/'missing.pdf'),'--output',str(output)],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,2)
            self.assertIn(b'--enable-research',result.stderr)
            self.assertFalse(output.exists())

if __name__=='__main__':unittest.main()
