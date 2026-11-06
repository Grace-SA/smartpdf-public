"""Prime with known synthetic content, then consume once for a user document."""
import io
import json
from pathlib import Path
import signal
import sys
import time
import urllib.request
import uuid
import re
import zipfile
import threading
import subprocess
from runner import create_converter, inspect_standby, remove_verified
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def prime(base, timeout):
    package=io.BytesIO()
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>SMARTPDF_SYNTHETIC_READINESS</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
    boundary=uuid.uuid4().hex
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="fileInput"; filename="document.docx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n').encode()+package.getvalue()+f'\r\n--{boundary}--\r\n'.encode()
    request=urllib.request.Request(base+'/api/v1/convert/file/pdf',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    with HTTP.open(request,timeout=timeout) as response:pdf=response.read(1024**2+1)
    if len(pdf)>1024**2 or not pdf.startswith(b'%PDF-'):raise RuntimeError('readiness')

def warm(directory, token):
    if not re.fullmatch(r'[a-f0-9]{32}',token): return 2
    cancel = Path(directory) / 'cancel'
    name = 'smartpdf-word-' + uuid.uuid4().hex
    created = False
    handed_off = False
    done=threading.Event()
    def monitor():
        while not done.wait(.25):
            if cancel.exists():
                try:remove_verified(name)
                except Exception:pass
                return
    watcher=threading.Thread(target=monitor,daemon=True)
    def stop(*_): cancel.touch()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    watcher.start()
    try:
        if cancel.exists(): return
        created = True
        deadline = time.monotonic()+150
        base = create_converter(name, token=token)
        while time.monotonic() < deadline and not cancel.exists():
            try:
                with HTTP.open(base+'/api/v1/info/status', timeout=2) as response:
                    ready = response.status == 200
                if ready:
                    if cancel.exists(): return
                    prime(base,max(1,min(30,deadline-time.monotonic())))
                    if cancel.exists(): return
                    print(json.dumps({'standby': {'name':name,'token':token}}), flush=True)
                    handed_off = True
                    return
            except Exception: time.sleep(.5)
        if not cancel.exists(): raise RuntimeError('startup')
    except Exception:
        if cancel.exists(): return
        print(json.dumps({'error':'Converter preheating could not finish.','code':'ENGINE_STARTUP_FAILED'}),flush=True)
        return 2
    finally:
        done.set();watcher.join(timeout=25)
        if created and not handed_off:
            try: remove_verified(name)
            except Exception: print(json.dumps({'cleanupFailed':True}),flush=True)

def discard(name,token):
    try:inspect_standby(name,token,require_running=False)
    except subprocess.CalledProcessError:
        # Cancellation may already have removed this clean standby.
        check=subprocess.run(['docker','ps','-aq','--filter',f'name=^/{name}$'],check=True,capture_output=True,timeout=20)
        if check.stdout.strip():raise RuntimeError('standby')
        return
    remove_verified(name)

if __name__ == '__main__':
    if sys.argv[1] == '--discard':
        try:discard(sys.argv[2],sys.argv[3])
        except Exception:
            print(json.dumps({'cleanupFailed':True}),flush=True)
            sys.exit(3)
    else:
        sys.exit(warm(sys.argv[1],sys.argv[2]))
