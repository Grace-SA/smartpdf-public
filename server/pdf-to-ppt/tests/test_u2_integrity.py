"""Synthetic model-admission checks; no MLX inference or model download."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]/'ocr'
spec = importlib.util.spec_from_file_location('u2_integrity', ROOT/'integrity.py')
integrity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(integrity)
COMMITTED = json.loads((ROOT/'u2-manifest.json').read_text())


def synthetic_model(tmp_path):
    manifest = deepcopy(COMMITTED)
    for name in manifest['files']:
        data = ('synthetic '+name).encode()
        (tmp_path/name).write_bytes(data)
        manifest['files'][name] = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return manifest


def test_exact_model_inventory_is_accepted(tmp_path):
    manifest = synthetic_model(tmp_path)
    integrity.verify_u2_model(tmp_path,manifest)


@pytest.mark.parametrize('filename', [
    'model-00001-of-00002.safetensors','config.json','tokenizer.json','chat_template.jinja'])
def test_model_and_tokenizer_tampering_is_rejected(tmp_path, filename):
    manifest = synthetic_model(tmp_path)
    path = tmp_path/filename
    path.write_bytes(b'x'+path.read_bytes()[1:])
    with pytest.raises(ValueError,match='hash mismatch'):
        integrity.verify_u2_model(tmp_path,manifest)


@pytest.mark.parametrize('filename', ['model.safetensors','tokenizer.model','added_tokens.json'])
def test_unreviewed_alternative_artifact_is_rejected(tmp_path, filename):
    manifest = synthetic_model(tmp_path)
    (tmp_path/filename).write_bytes(b'unreviewed')
    with pytest.raises(ValueError,match='Unexpected U2'):
        integrity.verify_u2_model(tmp_path,manifest)


def test_empty_inventory_does_not_disable_verification(tmp_path):
    with pytest.raises(ValueError,match='Incomplete U2'):
        integrity.verify_u2_model(tmp_path,{'files':{}})


def test_runner_rejects_unverified_model_before_importing_mlx(tmp_path,monkeypatch):
    synthetic_model(tmp_path)
    monkeypatch.syspath_prepend(str(ROOT))
    spec = importlib.util.spec_from_file_location('u2_runner_check',ROOT/'unlimited_runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setenv('SMARTPPT_U2_MODEL',str(tmp_path))
    monkeypatch.setattr('sys.argv',['unlimited_runner.py','--out',str(tmp_path/'out'),'sample.png'])
    with pytest.raises(ValueError,match='Offline artifact'):
        runner.main()
