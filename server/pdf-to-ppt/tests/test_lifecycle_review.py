"""Deterministic races and incomplete worker exits found during code review."""
from fastapi.testclient import TestClient
import pytest

from smartppt.api import create_app
from smartppt.config import ConversionError
from smartppt.stirling import StirlingProvider
from smartppt.store import Store
from smartppt.worker import work_once


@pytest.mark.parametrize('before,after', [
    ('queued', 'processing'), ('processing', 'validating'),
    ('validating', 'needs_review'),
])
def test_cancel_follows_the_current_state(settings, monkeypatch, before, after):
    app = create_app(settings)
    store = app.state.store
    job, token = store.create('preserve', 'en-US')
    store.update(job, before, ('uploading',))
    output = settings.root/job/'output.pptx'
    output.write_bytes(b'not downloadable after cancellation')
    original_get = store.get
    advanced = False

    def get_then_advance(job_id, bearer=None):
        nonlocal advanced
        row = original_get(job_id, bearer)
        if bearer is not None and not advanced:
            assert store.update(job, after, (before,))
            advanced = True
        return row

    monkeypatch.setattr(store, 'get', get_then_advance)
    with TestClient(app) as client:
        headers = {'Authorization': 'Bearer '+token}
        response = client.delete('/api/jobs/'+job, headers=headers)
        assert response.status_code == 200
        assert original_get(job)['state'] == 'cancelled'
        assert client.get('/api/jobs/'+job+'/download', headers=headers).status_code == 409
        assert client.delete('/api/jobs/'+job, headers=headers).status_code == 200
    if after in ('processing', 'validating'):
        assert output.exists()  # Supervisor must stop the writer before cleanup.
    else:
        assert not (settings.root/job).exists()
    assert store.claim() is None


def test_cancelled_queue_entry_cannot_be_claimed(settings):
    store = Store(settings)
    job, _ = store.create('preserve', 'en-US')
    store.update(job, 'queued', ('uploading',))
    assert store.cancel(job) == 'queued'
    assert store.claim() is None
    assert store.cancel('missing') is None


def test_zero_exit_without_validated_result_fails(settings, monkeypatch):
    store = Store(settings)
    job, _ = store.create('preserve', 'en-US')
    store.update(job, 'queued', ('uploading',))

    class IncompleteWorker:
        returncode = 0

        def poll(self):
            return 0

    monkeypatch.setattr('smartppt.worker.subprocess.Popen', lambda *a, **k: IncompleteWorker())
    assert work_once(settings)
    assert store.get(job)['state'] == 'failed'
    assert store.get(job)['error'] == 'worker_interrupted'


def test_spawn_failure_does_not_abandon_processing_state(settings, monkeypatch):
    store = Store(settings)
    job, _ = store.create('preserve', 'en-US')
    store.update(job, 'queued', ('uploading',))

    def cannot_start(*args, **kwargs):
        raise OSError('local process limit')

    monkeypatch.setattr('smartppt.worker.subprocess.Popen', cannot_start)
    assert work_once(settings)
    assert store.get(job)['state'] == 'failed'
    assert store.get(job)['error'] == 'worker_start_failed'


def test_provider_does_not_use_ambient_proxy(settings, monkeypatch):
    monkeypatch.setenv('ALL_PROXY', 'socks5h://127.0.0.1:9')
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:9')
    settings.stirling_url = 'http://127.0.0.1:8766'
    provider = StirlingProvider(settings)
    try:
        assert provider.client._trust_env is False
    finally:
        provider.client.close()
