import subprocess
import json
import os
import tempfile
import unittest
import io
import contextlib
from pathlib import Path
import warm
from unittest.mock import patch
from runner import remove_verified
from doctor import inspect_host
from runner import IMAGE, create_converter, inspect_standby

class PrimingTests(unittest.TestCase):
    @patch('warm.signal.signal')
    @patch('warm.remove_verified')
    @patch('warm.prime')
    @patch('warm.HTTP.open')
    @patch('warm.create_converter',return_value='http://172.30.0.2:8080')
    def test_handoff_waits_for_the_synthetic_conversion(self, create, http, prime, remove, signal):
        http.return_value.__enter__.return_value.status=200
        output=io.StringIO()
        prime.side_effect=lambda *_:self.assertEqual(output.getvalue(),'')
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(output):warm.warm(directory,'a'*32)
        prime.assert_called_once()
        self.assertEqual(json.loads(output.getvalue())['standby']['token'],'a'*32)
        remove.assert_not_called()
    @patch('warm.inspect_standby',side_effect=subprocess.CalledProcessError(1,'docker'))
    @patch('warm.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=b''))
    @patch('warm.remove_verified')
    def test_already_removed_standby_is_verified_without_deleting_any_other_container(self, remove, run, inspect):
        warm.discard('smartpdf-word-'+'a'*32,'b'*32)
        remove.assert_not_called()
        self.assertEqual(run.call_args.args[0][-1],'name=^/smartpdf-word-'+'a'*32+'$')
    @patch('warm.inspect_standby',side_effect=RuntimeError('foreign'))
    @patch('warm.remove_verified')
    def test_foreign_standby_is_never_deleted(self, remove, inspect):
        with self.assertRaises(RuntimeError):warm.discard('unrelated','a'*32)
        remove.assert_not_called()

class CleanupTests(unittest.TestCase):
    @patch('runner.subprocess.run')
    def test_clean_standby_keeps_the_existing_resource_and_network_limits(self, run):
        network='smartpdf-word'
        run.side_effect=[subprocess.CompletedProcess([],0,stdout=json.dumps([{'Internal':True}]).encode()),
                         subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],0),
                         subprocess.CompletedProcess([],0,stdout=json.dumps([{'NetworkSettings':{'Networks':{network:{'IPAddress':'172.30.0.2'}}}}]).encode())]
        with patch.dict(os.environ,{'WORD_DOCKER_NETWORK':network}):
            self.assertEqual(create_converter('smartpdf-word-'+'a'*32,'b'*32),'http://172.30.0.2:8080')
        args=run.call_args_list[1].args[0]
        self.assertEqual(args[args.index('--memory')+1],'2560m')
        self.assertEqual(args[args.index('--memory-swap')+1],'2560m')
        self.assertEqual(args[args.index('--cpus')+1],'2')
        self.assertEqual(args[-1],IMAGE)
        self.assertIn('smartpdf.word-standby='+'b'*32,args)
    @patch('runner.subprocess.run')
    def test_standby_refuses_a_foreign_container_or_nonce(self, run):
        info={'Image':IMAGE,'State':{'Running':True},'Config':{'Labels':{'smartpdf.word-service':'word-v1','smartpdf.word-standby':'a'*32}},'NetworkSettings':{'Networks':{'smartpdf-word':{'IPAddress':'172.30.0.2'}}}}
        run.return_value=subprocess.CompletedProcess([],0,stdout=json.dumps([info]).encode())
        with self.assertRaises(RuntimeError):inspect_standby('smartpdf-word-'+'b'*32,'c'*32)
        self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.args[0][:2],['docker','inspect'])
        with self.assertRaises(RuntimeError):inspect_standby('unrelated-container','a'*32)
        self.assertEqual(run.call_count,1)
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
