"""Start a separately supervised, offline CPU D-FINE detector on loopback."""
import json
import os
from pathlib import Path
from integrity import verify_files


def main():
    source = Path(os.environ['SMARTPPT_OXR_SOURCE']).resolve()
    weights = Path(os.environ['SMARTPPT_OXR_LAYOUT_MODEL']).resolve()
    # Preserve the virtualenv entrypoint: resolving its symlink loses its packages.
    python = Path(os.environ['SMARTPPT_OXR_LAYOUT_PYTHON']).absolute()
    manifest = json.loads((Path(__file__).parent/'oxr-manifest.json').read_text())
    verify_files(source, manifest['source_files'])
    verify_files(weights, manifest['layout_files'])
    env = dict(os.environ, MODEL_PATH=str(weights/'layout_analysis/last.pth'), DFINE_DEVICE='cpu',
               OMP_NUM_THREADS='4', HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    os.execve(python, [str(python), '-m', 'uvicorn', 'dfine_la.api:app', '--app-dir',
        str(source/'services/layout_analyze'), '--host', '127.0.0.1', '--port', '18081', '--workers', '1'], env)


if __name__ == '__main__':
    main()
