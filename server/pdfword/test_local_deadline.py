import contextlib
import io
import json
import os
import signal
import tempfile
import unittest
from unittest.mock import patch

import local_runner
from model import Rejected


class DeadlineTests(unittest.TestCase):
    def test_timeout_is_not_reported_as_user_cancellation(self):
        handlers = {}

        def convert(*args, **kwargs):
            try:
                handlers[signal.SIGALRM]()
            except Rejected:
                raise Rejected("Conversion cancelled.")

        output = io.StringIO()
        with tempfile.TemporaryDirectory() as work, patch.dict(
            os.environ, PDFWORD_LOCAL_V2="1", OFFICE_SHARED_MODE="false"
        ), patch.object(
            local_runner.signal,
            "signal",
            side_effect=lambda sig, fn: handlers.update({sig: fn}),
        ), patch.object(
            local_runner.signal, "alarm"
        ), patch.object(
            local_runner, "convert", side_effect=convert
        ), contextlib.redirect_stdout(
            output
        ):
            self.assertEqual(local_runner.run(work), 2)
        last = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(last["code"], "TIME_LIMIT")
        self.assertIn("time limit", last["error"])
