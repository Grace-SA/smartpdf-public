"""Provision fixed public ONNX model files; check size and SHA-256 before use."""
import argparse,hashlib,json,os
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--orientation',action='store_true');args=parser.parse_args()
    models=Path(os.getenv('SMARTPPT_OCR_MODELS',str(ROOT/'models')))
    manifest=json.loads((ROOT/'model-manifest.json').read_text())
    if args.orientation:
        orientation=json.loads((ROOT/'orientation-manifest.json').read_text())
        orientation['files']=[{'file':name,**entry,'url':f"https://huggingface.co/{orientation['repository']}/resolve/{orientation['revision']}/{name}"} for name,entry in orientation['files'].items()]
        manifest['models'].append(orientation)
    with httpx.Client(timeout=120,follow_redirects=True) as client:
        for model in manifest['models']:
            folder=models/model['repository'].split('/')[-1];folder.mkdir(parents=True,exist_ok=True)
            for artifact in model['files']:
                target=folder/artifact['file'];partial=target.with_suffix(target.suffix+'.part')
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==artifact['sha256']:continue
                try:
                    total=0;digest=hashlib.sha256()
                    with client.stream('GET',artifact['url']) as response:
                        response.raise_for_status()
                        with partial.open('wb') as out:
                            for chunk in response.iter_bytes():
                                total+=len(chunk)
                                if total>artifact['bytes']:raise ValueError('model size mismatch')
                                digest.update(chunk);out.write(chunk)
                    if total!=artifact['bytes'] or digest.hexdigest()!=artifact['sha256']:raise ValueError('model integrity mismatch')
                    partial.replace(target)
                finally:partial.unlink(missing_ok=True)
            (folder/'provenance.json').write_text(json.dumps(model,indent=2))
            print(model['repository'],model['revision'])
if __name__=='__main__':main()
