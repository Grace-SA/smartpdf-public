"""Verify provisioned offline artifacts against the reviewed manifest."""
import hashlib
from pathlib import Path


def verify_files(root, inventory):
    root = Path(root).resolve()
    for name, expected in inventory.items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size != expected['bytes']:
            raise ValueError('Offline artifact missing or size mismatch: '+name)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != expected['sha256']:
            raise ValueError('Offline artifact hash mismatch: '+name)


def verify_paddle_models(root, manifest):
    """Use the reviewed source inventory, never model-local provenance claims."""
    required = {'PP-OCRv6_medium_det_onnx', 'PP-OCRv6_medium_rec_onnx'}
    models = {}
    for model in manifest['models']:
        name = model['repository'].split('/')[-1]
        if name not in required or name in models:
            raise ValueError('Unexpected or duplicate OCR model inventory')
        files = model['files']
        inventory = {entry['file']: entry for entry in files}
        if len(inventory) != len(files) or not {'inference.onnx','inference.yml'} <= inventory.keys():
            raise ValueError('Incomplete OCR model inventory')
        models[name] = {name+'/'+file: inventory[file] for file in ('inference.onnx','inference.yml')}
    if models.keys() != required:
        raise ValueError('Incomplete OCR model inventory')
    for inventory in models.values():
        verify_files(root, inventory)


def verify_u2_model(root, manifest):
    required = {'chat_template.jinja','config.json','generation_config.json',
                'model-00001-of-00002.safetensors','model-00002-of-00002.safetensors',
                'model.safetensors.index.json','processor_config.json',
                'special_tokens_map.json','tokenizer.json','tokenizer_config.json'}
    inventory = manifest['files']
    if set(inventory) != required:
        raise ValueError('Incomplete U2 model inventory')
    # MLX/Transformers may choose optional files when present. Do not allow an
    # unreviewed alternative tokenizer/configuration or weight file to win.
    loadable = {'.json','.model','.txt','.jinja','.safetensors','.bin','.pt','.pth'}
    if any(p.is_file() and p.suffix in loadable and p.name not in inventory
           for p in Path(root).iterdir()):
        raise ValueError('Unexpected U2 model artifact')
    verify_files(root, inventory)
