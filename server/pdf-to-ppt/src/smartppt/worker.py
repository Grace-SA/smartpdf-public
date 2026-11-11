"""One supervisor, isolated child process per PDF. Run separately from web API."""
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import time
from .config import Settings, ConversionError
from .store import Store


def stop_worker(child):
    if os.name == 'posix':
        try:os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    else:child.kill()
    child.wait()


def run_job(settings, job_id):
    from .pdf import inspect_pdf
    from .preserve import convert_preserve
    from .providers import AdobeProvider
    from .stirling import StirlingProvider
    from .quality import inspect_pptx
    store = Store(settings)
    job = store.get(job_id)
    if not job or job['state'] != 'processing':
        return
    folder = settings.root/job_id
    source, target = folder/'input.pdf', folder/'output.part'
    try:
        assistance = None
        info = inspect_pdf(source, settings.max_bytes, settings.max_pages)
        if job['mode'] == 'editable':
            if not settings.editable_available:
                raise ConversionError('provider_not_configured')
            provider = StirlingProvider(settings) if settings.editable_provider == 'stirling' else AdobeProvider(settings)
            try:
                provider.convert(source, target, job['language'],
                    submitted=lambda url: store.update(job_id, 'processing', ('processing',), provider_job=url),
                    cancelled=lambda: store.get(job_id)['state'] != 'processing')
            finally:
                provider.client.close()
            if settings.layout_assistance:
                from .assisted import assist
                from .render_gate import run_gate
                import shutil
                # Validate the provider package before parsing or modifying its slides.
                inspect_pptx(target, info, job['mode'])
                original = folder/'original.pptx'
                shutil.copyfile(target,original)
                assistance = assist(source, target, settings)
                assistance = run_gate(original,target,source,assistance,settings)
                from .content_gate import enforce_content_safety
                assistance = enforce_content_safety(source,target,info,assistance,settings)
                original.unlink(missing_ok=True)
        else:
            convert_preserve(source, target, info)
        if not store.update(job_id, 'validating', ('processing',)):
            target.unlink(missing_ok=True)
            return
        report = inspect_pptx(target, info, job['mode'])
        if assistance is not None:
            report['assistance'] = assistance
        target.replace(folder/'output.pptx')
        state = 'needs_review' if job['mode'] == 'editable' else 'ready'
        if not store.update(job_id, state, ('validating',), report=json.dumps(report)):
            (folder/'output.pptx').unlink(missing_ok=True)
    except Exception as e:
        code = e.code if isinstance(e, ConversionError) else 'conversion_failed'
        store.update(job_id, 'failed', ('processing','validating'), error=code)
        target.unlink(missing_ok=True)


def work_once(settings):
    store = Store(settings); store.cleanup()
    job_id = store.claim()
    if not job_id:
        return False
    env = dict(os.environ, SMARTPPT_DATA=str(settings.root))
    # Do not inherit the upload request; no filename or PDF content in command lines.
    try:
        child = subprocess.Popen([sys.executable, '-m', 'smartppt.worker', '--job', job_id], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,start_new_session=(os.name=='posix'))
    except OSError:
        store.update(job_id, 'failed', ('processing',), error='worker_start_failed')
        store.cleanup()
        return True
    deadline = time.monotonic() + settings.job_timeout
    try:
        while child.poll() is None:
            if store.get(job_id)['state'] in ('cancelled','expired') or time.monotonic() > deadline:
                stop_worker(child)
                store.update(job_id, 'failed', ('processing','validating'), error='job_timeout')
                break
            time.sleep(.25)
        if child.returncode:
            store.update(job_id, 'failed', ('processing','validating'), error='worker_crashed')
        else:
            # A process exit is not proof that it published a validated result.
            store.update(job_id, 'failed', ('processing','validating'), error='worker_interrupted')
    finally:
        if child.poll() is None:
            stop_worker(child)
        store.cleanup()
    return True


def main():
    settings = Settings()
    if len(sys.argv) == 3 and sys.argv[1] == '--job':
        run_job(settings, sys.argv[2]); return
    if len(sys.argv) == 3 and sys.argv[1] == '--inspect':
        from .pdf import inspect_pdf
        try:
            print(json.dumps(inspect_pdf(Path(sys.argv[2]), settings.max_bytes, settings.max_pages)))
        except ConversionError as e:
            print(json.dumps({'error': e.code})); sys.exit(2)
        return
    while True:
        if not work_once(settings):
            time.sleep(1)


if __name__ == '__main__':
    main()
