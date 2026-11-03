"""Prepare verified public core inputs; builds never change the approved runtime pin."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile


def download(item, target):
    if not item['url'].startswith('https://'):
        raise ValueError('Core input must use HTTPS')
    partial = target.with_suffix(target.suffix + '.part')
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(item['url'], timeout=60) as response, partial.open('xb') as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 512 * 1024**2:
                raise ValueError('Core input exceeds download budget')
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != item['sha256']:
        partial.unlink()
        raise ValueError('Core input checksum mismatch')
    partial.rename(target)


def extract_fonts(jar, directory, profile):
    expected = {Path(x['path']).name: x for x in profile['fonts']
                if Path(x['path']).parent == Path('/usr/share/fonts/truetype')}
    with zipfile.ZipFile(jar) as archive:
        names = archive.namelist()
        if any('proprietary' in n.lower() or '/saas/' in n.lower()
               or n.startswith('BOOT-INF/classes/static/assets/') for n in names):
            raise ValueError('Core archive contains excluded modules or frontend assets')
        fonts = [n for n in names if n.startswith('BOOT-INF/classes/static/fonts/') and n.endswith('.ttf')]
        if not fonts or len(fonts) > 100:
            raise ValueError('Unexpected core font inventory')
        directory.mkdir()
        for name in fonts:
            font = expected.get(Path(name).name)
            if not font or archive.getinfo(name).file_size != font['bytes']:
                raise ValueError('Core font is absent from the approved inventory')
            content = archive.read(name)
            if hashlib.sha256(content).hexdigest() != font['sha256']:
                raise ValueError('Core font checksum mismatch')
            (directory / Path(name).name).write_bytes(content)


def prepare(context, source):
    manifest = json.loads((source / 'config/word-core.stirling-3.2.2.json').read_text(encoding='utf8'))
    if manifest['flavor'] != 'core':
        raise ValueError('Only the approved core flavor is supported')
    dockerfile = source / 'infra/word/core.Dockerfile'
    if hashlib.sha256(dockerfile.read_bytes()).hexdigest() != manifest['dockerfileSha256']:
        raise ValueError('Core Dockerfile checksum mismatch')
    context.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(dockerfile, context / 'Dockerfile')
    download(manifest['jar'], context / 'app.jar')
    download(manifest['license'], context / 'LICENSE.stirling')
    (context / 'scripts').mkdir()
    for script in manifest['scripts']:
        name = Path(script['path']).name
        if name not in ('init.sh', 'init-without-ocr.sh'):
            raise ValueError('Unexpected core startup script')
        download(script, context / 'scripts' / name)
    profile = json.loads((source / 'config/word-fonts.stirling-3.2.2.json').read_text(encoding='utf8'))
    extract_fonts(context / 'app.jar', context / 'fonts', profile)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True, type=Path)
    parser.add_argument('--build', action='store_true', help='Build a candidate; never updates the approved pin')
    args = parser.parse_args()
    manifest = prepare(args.context.resolve(), Path(__file__).resolve().parents[2])
    if args.build:
        subprocess.run(['docker', 'build', '--network=none', '-t', 'smartpdf-stirling-core:build-candidate', str(args.context.resolve())], check=True)
        actual = subprocess.run(['docker', 'image', 'inspect', 'smartpdf-stirling-core:build-candidate', '--format', '{{.Id}}'], check=True, capture_output=True, text=True).stdout.strip()
        print(json.dumps({'candidateImageId': actual, 'approvedImageId': manifest['imageId'], 'matchesApprovedImage': actual == manifest['imageId'], 'productionPinChanged': False}))
    else:
        print(json.dumps({'verifiedContext': str(args.context.resolve()), 'approvedImageId': manifest['imageId']}))
