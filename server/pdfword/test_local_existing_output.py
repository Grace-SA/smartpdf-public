import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import local_runner


class ExistingOutputTests(unittest.TestCase):
    def execute(self, root):
        capture = io.StringIO()
        with patch.dict(os.environ, PDFWORD_LOCAL_V2='1', OFFICE_SHARED_MODE='false'), patch.object(local_runner.signal, 'signal'), patch.object(local_runner.signal, 'alarm'), contextlib.redirect_stdout(capture):
            status = local_runner.run(root)
        return status, [json.loads(line) for line in capture.getvalue().splitlines()]

    def test_retry_preserves_preexisting_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); out=root/'output.docx';out.write_bytes(b'previous-successful-output')
            before=out.stat()
            status,messages=self.execute(root)
            self.assertEqual(status,2)
            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes(),b'previous-successful-output')
            self.assertEqual(out.stat().st_ino,before.st_ino)
            self.assertEqual(messages[-1]['code'],'INPUT_REJECTED')

    def test_dangling_output_link_is_not_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'output.docx';out.symlink_to(root/'missing')
            status,_=self.execute(root)
            self.assertEqual(status,2)
            self.assertTrue(out.is_symlink())

    def test_existing_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out=root/'output.docx';out.mkdir();(out/'keep').write_text('keep')
            status,_=self.execute(root)
            self.assertEqual(status,2)
            self.assertEqual((out/'keep').read_text(),'keep')

    def test_fresh_success_and_failure_cleanup_remain(self):
        for fail in (False,True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                def convert(source,destination,**kwargs):
                    destination.write_bytes(b'new-result')
                    if fail:raise local_runner.Rejected('rejected')
                    return {'warnings':[],'pages':1}
                with patch.object(local_runner,'convert',side_effect=convert):
                    status,_=self.execute(root)
                self.assertEqual(status,2 if fail else 0)
                self.assertEqual((root/'output.docx').exists(),not fail)
                self.assertEqual((root/'expected.json').exists(),not fail)

if __name__=='__main__':unittest.main()
