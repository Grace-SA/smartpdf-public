"""Start only this PoC's loopback container in the user-selected WSL distribution."""
import argparse
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--image',required=True)
    p.add_argument('--variant',required=True,choices=['default-fonts','noto-fonts'])
    p.add_argument('--distribution',default='Ubuntu-24.04')
    p.add_argument('--wsl',default='wsl.exe')
    args=p.parse_args()
    if args.variant=='default-fonts' and not re.fullmatch(r'gotenberg/gotenberg@sha256:[a-f0-9]{64}',args.image):
        raise SystemExit('Baseline requires the official image pinned by digest')
    if args.variant=='noto-fonts' and not re.fullmatch(r'smartpdf-m13-gotenberg-noto:[a-f0-9]{12}',args.image):
        raise SystemExit('Expected task-local font image tag')
    prefix=[args.wsl,'-d',args.distribution,'-u','root','--exec','docker']
    def docker(*parts):
        return subprocess.check_output(prefix+list(parts),text=True,encoding='utf8').strip()
    root=Path('.research/m13/gotenberg')
    record=root/(args.variant+'-environment.json')
    if record.exists():raise SystemExit('Preserve previous environment evidence')
    # Refuse an occupied name rather than deleting or replacing another container.
    name='smartpdf-m13-poc-'+args.variant
    occupied=docker('ps','-a','--filter','name=^/'+name+'$','--format','{{.ID}}')
    if occupied:raise SystemExit('Task container name already exists; inspect ownership before stopping it')
    identifier=docker('create','--name',name,'--cpus','2','--memory','4g','--pids-limit','512',
        '-p','127.0.0.1:4244:3000',args.image,'gotenberg','--api-timeout=90s',
        '--libreoffice-auto-start=true','--libreoffice-max-queue-size=2','--libreoffice-deny-list=.*',
        '--api-disable-download-from=true','--chromium-disable-routes=true')
    docker('start',identifier)
    metadata={'containerId':identifier,'containerName':name,'requestedImage':args.image,
        'dockerVersion':docker('version','--format','{{.Server.Version}}'),
        'container':json.loads(docker('inspect',identifier))[0]}
    record.write_text(json.dumps(metadata,indent=2),encoding='utf8')
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:4244/health',timeout=2) as response:
                if response.status==200:break
        except OSError:time.sleep(1)
    else:
        print(docker('logs',identifier)[-4000:]);raise SystemExit('PoC container not healthy')
    for label,command in [('libreoffice',['libreoffice','--version']),
                          ('fontMatch',['fc-match','Noto Sans SC']),('fonts',['fc-list'])]:
        metadata[label]=docker('exec',identifier,*command)
    with urllib.request.urlopen('http://127.0.0.1:4244/version',timeout=3) as response:
        metadata['gotenbergVersionResponse']=response.read().decode()
    record.write_text(json.dumps(metadata,indent=2),encoding='utf8')
    print(json.dumps({k:metadata[k] for k in ['containerId','containerName','requestedImage','libreoffice','fontMatch','gotenbergVersionResponse']},indent=2))

if __name__=='__main__':main()
