"""Pinned research downloads into an ignored directory; no install hooks or product changes."""
import base64, hashlib, io, json, tarfile, urllib.request
from pathlib import Path

root=Path('.research/m13')
root.mkdir(parents=True,exist_ok=True)
packages={'matbee':('@matbee/libreoffice-converter','2.7.2'),
          'docx':('docx-preview','0.4.1'),'mammoth':('mammoth','1.13.0'),
          'jszip':('jszip','3.10.1')}
records=[]
for label,(name,version) in packages.items():
    endpoint='https://registry.npmjs.org/'+name.replace('/','%2f')+'/'+version
    metadata=json.load(urllib.request.urlopen(endpoint,timeout=30))
    data=urllib.request.urlopen(metadata['dist']['tarball'],timeout=120).read()
    integrity='sha512-'+base64.b64encode(hashlib.sha512(data).digest()).decode()
    assert integrity==metadata['dist']['integrity'], 'Registry archive integrity mismatch'
    target=root/label
    target.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        archive.extractall(target,filter='data')
    records.append(dict(name=name,version=version,archiveSha256=hashlib.sha256(data).hexdigest(),
                        integrity=integrity,gitHead=metadata.get('gitHead'),license=metadata.get('license')))
(root/'jszip.js').write_bytes((root/'jszip/package/dist/jszip.min.js').read_bytes())
(root/'downloads.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print(json.dumps(records,indent=2))
