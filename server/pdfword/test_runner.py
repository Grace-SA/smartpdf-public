"""Fault injection for isolation and cleanup, without requiring Docker in CI."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import runner


class RunnerTests(unittest.TestCase):
    def execute(self, failure=None, cancel=False):
        commands = []
        alive = False
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'input.pdf').write_bytes(b'%PDF-synthetic')
            def command(args, **kwargs):
                nonlocal alive
                commands.append(args)
                stdout = b''
                if args[1] == 'create': alive = True
                if args[1] == 'ps': stdout = b'synthetic-id' if alive else b''
                if args[1] == 'rm': alive = False
                if '/tmp/worker.py' in args and '/tmp/output.docx' in args:
                    if failure == 'rejected':
                        raise subprocess.CalledProcessError(2, args, output=b'{"error":"Scans unsupported","code":"INPUT_REJECTED"}')
                    if failure == 'timeout': raise subprocess.TimeoutExpired(args, 90)
                    stdout = b'{"pages":1}'
                elif args[1] == 'exec' and '-i' not in args and '-c' in args:
                    stdout = b'PKsynthetic'
                if cancel and args[1] == 'start': (root / 'cancel').touch()
                return subprocess.CompletedProcess(args, 0, stdout, b'')
            output = io.StringIO()
            with patch.object(runner.subprocess, 'run', side_effect=command), patch.object(runner.signal, 'signal'), contextlib.redirect_stdout(output):
                status = runner.run(root)
            exists = (root / 'output.docx').exists()
            messages = [json.loads(line) for line in output.getvalue().splitlines()]
        return status, exists, alive, commands, messages

    def test_offline_nonroot_bounded_job_and_verified_cleanup(self):
        status, exists, alive, commands, messages = self.execute()
        self.assertEqual(status, 0)
        self.assertTrue(exists)
        self.assertFalse(alive)
        create = next(c for c in commands if c[1] == 'create')
        for flag, value in [('--network', 'none'), ('--memory', '768m'), ('--cpus', '1'), ('--pids-limit', '64'), ('--user', '10001:10001')]:
            self.assertEqual(create[create.index(flag) + 1], value)
        self.assertIn('--read-only', create)
        self.assertNotIn('-v', create)
        self.assertNotIn('-p', create)
        self.assertFalse(any(m.get('cleanupFailed') for m in messages))

    def test_refusal_and_timeout_have_no_partial_output(self):
        for failure in ('rejected', 'timeout'):
            with self.subTest(failure=failure):
                status, exists, alive, _, messages = self.execute(failure)
                self.assertNotEqual(status, 0)
                self.assertFalse(exists)
                self.assertFalse(alive)
                if failure == 'rejected':
                    self.assertEqual(messages[-1]['code'], 'INPUT_REJECTED')

    def test_cancellation_discards_result_and_removes_container(self):
        _, exists, alive, _, _ = self.execute(cancel=True)
        self.assertFalse(exists)
        self.assertFalse(alive)


if __name__ == '__main__':
    unittest.main()
