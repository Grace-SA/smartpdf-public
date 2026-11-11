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
