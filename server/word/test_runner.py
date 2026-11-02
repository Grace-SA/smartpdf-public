import subprocess
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from runner import remove_verified
from doctor import inspect_host
from runner import IMAGE

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
                       json.dumps([{'RepoDigests':[IMAGE] if image else []}]),
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
