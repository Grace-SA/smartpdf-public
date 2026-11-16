"""Offline OXR layout + recognition adapter for Apple Silicon validation.

Uses the pinned upstream pipeline and a loopback-only D-FINE detector. No hosted
OXR API. Models/source are provisioned separately; user documents never download
code or select an endpoint. The job supervisor owns this process group.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

SOURCE_REVISION = 'b2ee4ac12ed220bf7fefa74951babf0d3b05e766'
MODEL_REVISION = 'bdbec15bad81efe04ff0e66f20d36931cce2340a'


def local_url(value):
    url = urlsplit(value)
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', '::1')
            or url.username or url.password or url.query or url.fragment or url.path not in ('', '/')):
        raise ValueError('OXR layout detector must be a loopback HTTP origin')
    return value.rstrip('/')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('images', type=Path, nargs='+')
    args = parser.parse_args()
    source = Path(os.environ['SMARTPPT_OXR_SOURCE']).resolve()
    model_dir = Path(os.environ['SMARTPPT_OXR_MODEL']).resolve()
    if not (source/'oxr/pipeline/orchestrator.py').is_file() or not (model_dir/'config.json').is_file():
        raise ValueError('Provision the pinned OXR source and local MLX weights first')
    from integrity import verify_files
    manifest = json.loads((Path(__file__).parent/'oxr-manifest.json').read_text())
    verify_files(source, manifest['source_files'])
    verify_files(model_dir, manifest['model_files'])
    endpoint = local_url(os.getenv('SMARTPPT_OXR_LAYOUT_URL', 'http://127.0.0.1:18081'))
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      OXR__LAYOUT_ANALYZE_MODEL__URL=endpoint)
    sys.path.insert(0, str(source))
    import cv2
    import mlx.core as mx
    from mlx_vlm import apply_chat_template, generate, load
    from oxr.config.settings import settings
    from oxr.model.client import ModelOutput, model_client
    from oxr.model.layout_client import layout_client
    from oxr.pipeline.orchestrator import process_decoded_document
    from PIL import Image

    model, processor = load(str(model_dir), trust_remote_code=False)
    calls = []

    async def inference(prompt, image, timeout, model_options=None, max_tokens=None):
        formatted = apply_chat_template(processor, model.config, prompt, num_images=1)
        rgb = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        cap = min(max_tokens or 4096, 4096)
        result = generate(model, processor, formatted, image=[rgb], max_tokens=cap, temperature=0)
        capped = result.generation_tokens >= cap
        calls.append({'tokens': result.generation_tokens, 'capped': capped})
        return ModelOutput(result.text, finish_reason='length' if capped else 'stop')

    model_client._call_vision_model = inference
    settings.oxr_model.max_concurrency = 1
    settings.debug = False
    args.out.mkdir(parents=True, exist_ok=True)
    # Upstream emits figure crops even for JSON. Keep them inside the job's
    # retention directory, never in a shared working-directory outputs/ folder.
    settings.pipeline.image_output_dir = str(args.out.resolve()/'assets')

    async def run():
        try:
            for path in args.images:
                calls.clear(); start = time.monotonic(); mx.reset_peak_memory()
                image = cv2.imread(str(path))
                if image is None:
                    raise ValueError('invalid input image')
                height, width = image.shape[:2]
                result = await process_decoded_document([image], 'page.png', ['json'], keep_header_footer=True)
                pages = result['outputs']['json']['pages']
                if len(pages) != 1:
                    raise ValueError('unexpected OXR page count')
                blocks = []
                for block in pages[0]['blocks']:
                    box = block['bbox']
                    # Detector boxes can exceed the image by subpixels; clip at source.
                    box = [max(0, min(width, box[0])), max(0, min(height, box[1])),
                           max(0, min(width, box[2])), max(0, min(height, box[3]))]
                    blocks.append({'label': block['type'].lower(), 'content': block.get('content') or '',
                                   'bbox': box, 'page': 1})
                record = {'engine': 'SoMark-OXR-1.0-MLX-BF16', 'source_revision': SOURCE_REVISION,
                          'model_revision': MODEL_REVISION,
                          'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'image_size': [width, height], 'coordinate_space': 'pixels', 'blocks': blocks,
                          'capped': any(c['capped'] for c in calls), 'calls': list(calls),
                          'seconds': time.monotonic()-start, 'mlx_peak_bytes': mx.get_peak_memory()}
                (args.out/(path.stem+'.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2))
                print(path.name, len(blocks), round(record['seconds'], 3), 'capped', record['capped'], flush=True)
        finally:
            await layout_client.aclose()

    asyncio.run(run())


if __name__ == '__main__':
    main()
