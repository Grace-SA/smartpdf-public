import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import ocr
from model import Rejected


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copyfile(
            Path(ocr.__file__).with_name("process_server.py"),
            self.root / "process_server.py",
        )
        (self.root / "ocr_process.py").write_text("""
import json,os,time
from pathlib import Path
from process_server import serve
count=0
def main(request):
 global count
 count+=1
 if request.get("fail"): raise ValueError("synthetic error")
 time.sleep(request.get("sleep",0))
 Path(request["output"]).write_text(json.dumps({"pid":os.getpid(),"count":count}))
serve(main)
""")
        self.adapter = ocr.OCR(self.root)
        self.patcher = patch.object(ocr, "__file__", str(self.root / "ocr.py"))
        self.patcher.start()

    def tearDown(self):
        self.adapter.close()
        self.patcher.stop()
        self.temp.cleanup()

    def request(self, index, budget=3, **extra):
        request = self.root / f"{index}.json"
        output = self.root / f"{index}.output"
        request.write_text(json.dumps(dict(engine="oxr", output=str(output), **extra)))
        self.adapter._request(
            sys.executable,
            "ocr_process.py",
            request,
            os.environ,
            time.monotonic(),
            budget,
        )
        return json.loads(output.read_text())

    def test_reuses_process_and_close_reaps_it(self):
        first = self.request(1)
        second = self.request(2)
        self.assertEqual(first["pid"], second["pid"])
        self.assertEqual(second["count"], 2)
        child = next(iter(self.adapter.processes.values()))
        self.adapter.close()
        self.assertIsNotNone(child.poll())
        self.assertFalse(self.adapter.processes)

    def test_failed_page_reaps_process_and_next_request_is_fresh(self):
        first = self.request(1)
        child = next(iter(self.adapter.processes.values()))
        with self.assertRaises(Rejected):
            self.request(2, fail=True)
        self.assertIsNotNone(child.poll())
        self.assertNotEqual(first["pid"], self.request(3)["pid"])

    def test_timeout_and_cancel_reap_workers(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                self.request(1)
                child = next(iter(self.adapter.processes.values()))
                if cancelled:
                    self.adapter.cancel = self.root / "cancel"
                    self.adapter.cancel.touch()
                with self.assertRaisesRegex(
                    Rejected, "cancelled" if cancelled else "timed out"
                ):
                    self.request(2, budget=0.1, sleep=10)
                self.assertIsNotNone(child.poll())
                self.assertFalse(self.adapter.processes)
