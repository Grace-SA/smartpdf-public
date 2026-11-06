import subprocess
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from runner import remove_verified
from doctor import inspect_host
from runner import IMAGE
from pathlib import Path
from types import SimpleNamespace
import runner

class ExcelDirectTests(unittest.TestCase):
    def exercise(self, failure=None):
        calls = []; events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'input.xlsx').write_bytes(b'synthetic-workbook')
            (root/'options.json').write_text('{"sheets":[0],"scale":"auto"}')
            def prepare(source, target, options):
                target.write_bytes(source.read_bytes()); return []
            def execute(args, **kwargs):
                calls.append((args, kwargs))
                if 'stat' in args:
                    if failure == 'timeout': raise subprocess.TimeoutExpired(args, 90)
                    return subprocess.CompletedProcess(args, 0, stdout=str(30*1024**2+1 if failure == 'size' else 14).encode())
                if args[-2:] == ['cat', '/tmp/input.pdf']:
                    return subprocess.CompletedProcess(args, 0, stdout=b'%PDF-synthetic' if failure != 'invalid' else b'not-a-pdf-file')
                return subprocess.CompletedProcess(args, 0, stdout=b'')
            with patch('runner.load_excel_preflight', return_value=SimpleNamespace(prepare=prepare,Rejected=ValueError)), patch('runner.subprocess.run', side_effect=execute), patch('runner.signal.signal'), patch('runner.emit', side_effect=lambda **v:events.append(v)), patch('runner.urllib.request.urlopen', side_effect=AssertionError('No HTTP app for Excel')):
                result = runner.run(root, 'excel')
            return result, calls, events, (root/'output.pdf').exists()

    def test_excel_uses_disconnected_single_document_renderer_and_cleans_up(self):
        result, calls, events, output = self.exercise()
        self.assertEqual(result, 0); self.assertTrue(output)
        create = next(args for args, _ in calls if args[1] == 'create')
        self.assertEqual(create[create.index('--network')+1], 'none')
        self.assertIn('--pids-limit', create); self.assertIn('no-new-privileges', create)
        self.assertNotIn('--user', create)
        office = next((args, kw) for args, kw in calls if 'libreoffice' in args)
        self.assertEqual(office[1]['timeout'], 90)
        self.assertIn('pdf:calc_pdf_Export', office[0])
        stream = next(kw for args, kw in calls if '-i' in args)
        self.assertEqual(stream['input'], b'synthetic-workbook')
        self.assertTrue(any(args[1:3] == ['rm','-f'] for args, _ in calls))
        self.assertEqual(events[-1], {'state':'checking-result'})

    def test_excel_failed_or_oversize_output_is_never_exposed_and_container_removed(self):
        for failure in ['size','invalid','timeout']:
            with self.subTest(failure=failure):
                result, calls, events, output = self.exercise(failure)
                self.assertEqual(result, 3); self.assertFalse(output)
                self.assertTrue(any(args[1:3] == ['rm','-f'] for args, _ in calls))
                self.assertTrue(any('error' in event for event in events))

class CleanupTests(unittest.TestCase):
    @patch('runner.subprocess.run')
    def test_monitor_already_removed_container(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0, stdout=b'')]
        remove_verified('smartpdf-word-test')
        self.assertTrue(run.call_args.kwargs['check'])

    @patch('runner.subprocess.run')
    def test_daemon_unavailable_is_not_success(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 1), subprocess.CalledProcessError(1, 'docker')]
        with self.assertRaises(subprocess.CalledProcessError):
            remove_verified('smartpdf-word-test')

    @patch('runner.subprocess.run')
    def test_still_present_is_not_success(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0, stdout=b'abc123')]
        with self.assertRaises(RuntimeError):
            remove_verified('smartpdf-word-test')

    @patch('runner.subprocess.run')
    def test_reaper_checks_container_id(self, run):
        run.side_effect = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0, stdout=b'')]
        remove_verified('a' * 64, by_id=True)
        self.assertEqual(run.call_args.args[0][-1], 'id=' + 'a' * 64)

class HostChecks(unittest.TestCase):
    def checks(self, production=False, memory=4 * 1024**3, internal=True, image=True, origin='https://example.invalid', uid=1000, kernel='6.8.0'):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            replies = ['v24.15.0', json.dumps({'OSType':'linux','MemTotal':memory,'NCPU':2}),
                       json.dumps([{'Id':IMAGE if image else 'sha256:'+'0'*64}]),
                       json.dumps([{'Internal':internal}])]
            with patch.dict(os.environ, {'WORD_PUBLIC_ORIGIN':origin,'WORD_DATA_DIR':directory,'WORD_PROCESSING_LABEL':'Sydney, Australia'}), \
                 patch('doctor.command', side_effect=replies), patch('doctor.platform.release', return_value=kernel), \
                 patch('doctor.os.geteuid', return_value=uid, create=True):
                return {c['name']: c['passed'] for c in inspect_host(production)}

    def test_fixed_environment_is_checked(self):
        checks = self.checks()
        for key in ['node','fixed-image','internal-network','docker-memory','docker-cpu','task-directory']:
            self.assertTrue(checks[key], key)

    def test_shared_small_host_and_external_network_rejected(self):
        checks = self.checks(memory=2 * 1024**3, internal=False, image=False)
        for key in ['docker-memory','internal-network','fixed-image']:
            self.assertFalse(checks[key], key)

    def test_production_rejects_local_root_and_origin_path(self):
        checks = self.checks(production=True, uid=0, kernel='6.6.0-microsoft-standard-WSL2', origin='https://example.invalid/')
        for key in ['dedicated-linux','service-user','origin']:
            self.assertFalse(checks[key], key)

if __name__ == '__main__': unittest.main()
