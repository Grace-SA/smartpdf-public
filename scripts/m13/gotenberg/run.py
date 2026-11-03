"""Synthetic-only PoC client. A running, isolated Gotenberg is required."""
import argparse
import hashlib
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse

def multipart(data):
    boundary='m13-synthetic-'+hashlib.sha256(data).hexdigest()
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="synthetic.docx"\r\n'
          'Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n').encode()
    return boundary,body+data+f'\r\n--{boundary}--\r\n'.encode()

def collect():
    result=[]
    for directory,kind in [(Path('.research/m13/fixtures'),'original'),
                           (Path('.research/m13/gotenberg/fixtures'),'extended')]:
        manifest=json.loads((directory/'manifest.json').read_text(encoding='utf8'))
        for item in manifest:
            path=directory/(item['name']+'.docx')
            assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],'Frozen source changed'
            result.append((item,path,kind))
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--endpoint',required=True)
    parser.add_argument('--variant',required=True,choices=['default-fonts','noto-fonts'])
    parser.add_argument('--repeat',type=int,default=2)
    args=parser.parse_args()
    target=urlparse(args.endpoint)
    if target.scheme!='http' or target.hostname not in ['localhost','127.0.0.1','::1']:
        raise SystemExit('Use loopback, or an SSH tunnel to the isolated test service; no public endpoint.')
    if not 1<=args.repeat<=3:raise SystemExit('Repeat must be 1..3')
    root=Path('.research/m13/gotenberg')/args.variant
    if (root/'results.json').exists():raise SystemExit('Existing evidence must not be overwritten')
    root.mkdir(parents=True,exist_ok=True)
    result={'variant':args.variant,'endpointScope':'loopback','runs':[],'negativeRuns':[]}
    for cycle in range(args.repeat):
        for expected,path,kind in collect():
            data=path.read_bytes();boundary,body=multipart(data)
            request=urllib.request.Request(args.endpoint.rstrip('/')+'/forms/libreoffice/convert',
                data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
            start=time.perf_counter()
            row={'name':expected['name'],'cohort':kind,'cycle':cycle+1,'inputSha256':expected['sha256']}
            try:
                with urllib.request.urlopen(request,timeout=120) as response:
                    output=response.read(32*1024*1024+1)
                    row.update(status=response.status,contentType=response.headers.get('Content-Type'))
                if not output.startswith(b'%PDF-') or len(output)>30*1024*1024:
                    raise ValueError('Not an acceptable PDF or output exceeds budget')
                filename=f'{cycle+1}-{kind}-{expected["name"]}.pdf'
                (root/filename).write_bytes(output)
                row.update(file=filename,outputBytes=len(output),outputSha256=hashlib.sha256(output).hexdigest())
            except (urllib.error.URLError,ValueError,TimeoutError) as error:
                row['error']=type(error).__name__+': '+str(error)[:300]
            row['elapsedMs']=round((time.perf_counter()-start)*1000,1)
            result['runs'].append(row)
            (root/'results.json').write_text(json.dumps(result,indent=2),encoding='utf8')
            print(json.dumps(row),flush=True)
    for name in ['empty','corrupt']:
        data=(Path('.research/m13/fixtures')/(name+'.docx')).read_bytes()
        boundary,body=multipart(data)
        request=urllib.request.Request(args.endpoint.rstrip('/')+'/forms/libreoffice/convert',data=body,
            headers={'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
        try:
            with urllib.request.urlopen(request,timeout=120) as response:
                row={'name':name,'status':response.status,'expectedRejection':False}
        except urllib.error.HTTPError as error:
            row={'name':name,'status':error.code,'expectedRejection':400<=error.code<500}
        except (urllib.error.URLError,TimeoutError) as error:
            row={'name':name,'error':type(error).__name__,'expectedRejection':False}
        result['negativeRuns'].append(row)
    (root/'results.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    raise SystemExit(1 if any('error' in row for row in result['runs']) or
                     not all(row['expectedRejection'] for row in result['negativeRuns']) else 0)

if __name__=='__main__':main()
