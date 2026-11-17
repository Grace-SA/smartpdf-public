"""Offline synthetic artifacts exercise the runtime model admission gate."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]/'ocr'
spec = importlib.util.spec_from_file_location('paddle_integrity', ROOT/'integrity.py')
integrity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integrity)


def synthetic_inventory(tmp_path):
    models = []
    for name in ('PP-OCRv6_medium_det_onnx','PP-OCRv6_medium_rec_onnx'):
        folder = tmp_path/name
        folder.mkdir()
        files = []
        for filename in ('inference.onnx','inference.yml'):
            data = (name+'/'+filename).encode()
            (folder/filename).write_bytes(data)
            files.append({'file':filename, 'bytes':len(data),
                          'sha256':hashlib.sha256(data).hexdigest()})
        # A local provenance file must never weaken the committed inventory.
        (folder/'provenance.json').write_text('{"files":[]}')
        models.append({'repository':'PaddlePaddle/'+name, 'files':files})
    return {'models':models}


def test_verified_models_do_not_need_writable_provenance(tmp_path):
    manifest = synthetic_inventory(tmp_path)
    integrity.verify_paddle_models(tmp_path,manifest)
    for path in tmp_path.glob('*/provenance.json'):
        path.unlink()
    integrity.verify_paddle_models(tmp_path,manifest)


@pytest.mark.parametrize('damage', ['size','hash','missing'])
def test_mutable_provenance_cannot_approve_damaged_model(tmp_path, damage):
    manifest = synthetic_inventory(tmp_path)
    path = tmp_path/'PP-OCRv6_medium_det_onnx/inference.onnx'
    if damage == 'missing':
        path.unlink()
    else:
        data = path.read_bytes()
        path.write_bytes(data+b'x' if damage == 'size' else b'x'+data[1:])
    with pytest.raises(ValueError,match='Offline artifact'):
        integrity.verify_paddle_models(tmp_path,manifest)


@pytest.mark.parametrize('damage', ['empty','missing_model','missing_file','duplicate_model','duplicate_file'])
def test_incomplete_inventory_fails_closed(tmp_path, damage):
    manifest = synthetic_inventory(tmp_path)
    if damage == 'empty':manifest['models'] = []
    if damage == 'missing_model':manifest['models'].pop()
    if damage == 'missing_file':manifest['models'][0]['files'].pop()
    if damage == 'duplicate_model':manifest['models'].append(deepcopy(manifest['models'][0]))
    if damage == 'duplicate_file':manifest['models'][0]['files'].append(deepcopy(manifest['models'][0]['files'][0]))
    with pytest.raises(ValueError,match='inventory'):
        integrity.verify_paddle_models(tmp_path,manifest)


def test_committed_inventory_rejects_fake_model_local_claims(tmp_path):
    synthetic_inventory(tmp_path)
    with pytest.raises(ValueError,match='Offline artifact'):
        integrity.verify_paddle_models(tmp_path,json.loads((ROOT/'model-manifest.json').read_text()))
