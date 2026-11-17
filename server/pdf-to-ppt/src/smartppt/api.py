import asyncio
import json
from pathlib import Path
import shutil
import sys
import time
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import Settings, ConversionError
# Accepted legacy request locales; OCR language is detected locally.
LANGUAGES = {'en-US', 'zh-CN', 'zh-TW', 'ja-JP', 'ko-KR', 'de-DE', 'fr-FR', 'es-ES'}
from .store import Store


def create_app(settings=None):
    settings = settings or Settings()
    store = Store(settings)
    app = FastAPI(title='SmartPDF PDF to PowerPoint', version='0.1.0')
    app.state.store = store

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'"
        return response

    def authorized(job_id, authorization):
        if not authorization or not authorization.startswith('Bearer '):
            raise HTTPException(404, 'job_not_found')
        row = store.get(job_id, authorization[7:])
        if not row:
            raise HTTPException(404, 'job_not_found')
        if row['expires'] < time.time():
            raise HTTPException(410, 'job_expired')
        return row

    @app.get('/api/capabilities')
    def capabilities():
        return {'editable_available': settings.editable_available, 'preserve_available':True,
                'max_bytes':settings.max_bytes, 'max_pages':settings.max_pages,
                'retention_seconds':settings.retention_seconds,
                'languages':sorted(LANGUAGES),
                'editable_provider':settings.editable_provider,
                'cloud_provider':None,
                'ocr_available':settings.local_ocr_available,
                'ocr_language_selection':False,
                'release_status':'development; quality acceptance pending'}

    @app.get('/healthz')
    def health():
        return {'status':'ok'}

    @app.post('/api/jobs', status_code=202)
    async def create_job(request: Request, mode: str='editable', language: str='en-US'):
        if mode not in ('editable','preserve') or language not in LANGUAGES:
            raise HTTPException(422, 'invalid_options')
        if mode == 'editable' and not settings.editable_available:
            raise HTTPException(503, 'provider_not_configured')
        if request.headers.get('content-type','').split(';')[0] != 'application/pdf':
            raise HTTPException(415, 'pdf_required')
        try:
            declared = int(request.headers.get('content-length', 0))
        except ValueError:
            raise HTTPException(400, 'invalid_content_length')
        if declared > settings.max_bytes:
            raise HTTPException(413, 'file_size_limit')
        try:
            job_id, token = store.create(mode, language)
        except ConversionError:
            raise HTTPException(429, 'queue_full', headers={'Retry-After':'10'})
        folder = settings.root/job_id
        proc = None
        try:
            total = 0
            with (folder/'input.pdf').open('wb') as out:
                async with asyncio.timeout(60):
                    async for chunk in request.stream():
                        total += len(chunk)
                        if total > settings.max_bytes:
                            raise HTTPException(413, 'file_size_limit')
                        out.write(chunk)
            proc = await asyncio.create_subprocess_exec(sys.executable, '-m', 'smartppt.worker', '--inspect', str(folder/'input.pdf'),
                         stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            raw, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode:
                try:
                    code = json.loads(raw)['error']
                except (ValueError, KeyError):
                    code = 'invalid_pdf'
                raise HTTPException(422, code)
            info = json.loads(raw)
            # Metadata from the child is bounded again against per-app limits.
            if info['page_count'] > settings.max_pages:
                raise HTTPException(422, 'page_limit')
            store.update(job_id, 'queued', ('uploading',))
            return {'id':job_id, 'token':token, 'state':'queued',
                    'page_count':info['page_count'], 'mixed_sizes':info['mixed_sizes'],
                    'ocr_candidate_pages':info['ocr_candidate_pages']}
        except BaseException as error:
            if proc and proc.returncode is None:
                proc.kill(); await proc.wait()
            store.update(job_id, 'failed', ('uploading',), error='upload_rejected')
            shutil.rmtree(folder, ignore_errors=True)
            if isinstance(error, TimeoutError):
                raise HTTPException(408, 'upload_or_inspection_timeout')
            raise

    @app.get('/api/jobs/{job_id}')
    def status(job_id: str, authorization: str|None=Header(default=None)):
        return Store.public(authorized(job_id, authorization))

    @app.delete('/api/jobs/{job_id}')
    def cancel(job_id: str, authorization: str|None=Header(default=None)):
        authorized(job_id, authorization)
        previous = store.cancel(job_id)
        if previous is None:
            raise HTTPException(404, 'job_not_found')
        # Supervisor terminates an active converter. Downloads are blocked immediately.
        # Repeated DELETE must not remove files before an active worker has
        # acknowledged the first cancellation and stopped writing.
        if previous not in ('processing','validating','cancelled'):
            shutil.rmtree(settings.root/job_id, ignore_errors=True)
        return {'state':'cancelled'}

    @app.get('/api/jobs/{job_id}/download')
    def download(job_id: str, authorization: str|None=Header(default=None)):
        row = authorized(job_id, authorization)
        if row['state'] not in ('ready','needs_review'):
            raise HTTPException(409, 'output_not_ready')
        path = settings.root/job_id/'output.pptx'
        if not path.is_file():
            raise HTTPException(410, 'output_expired')
        return FileResponse(path, media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation', filename='converted.pptx')

    web = Path(__file__).resolve().parents[2]/'web'
    if web.is_dir():
        app.mount('/', StaticFiles(directory=web, html=True), name='web')
    return app


app = create_app()
