"""Provision pinned public model files and verify their SHA-256 before serving.

This build/setup command may use the network. Conversion itself is offline.
"""

import hashlib
import json
import os
from pathlib import Path
import sys

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
from huggingface_hub import hf_hub_download


def main(destination):
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[2] / "server/pdf-to-excel/models.json"
        ).read_text()
    )
    for model in manifest["models"]:
        directory = destination / model["repository"].replace("/", "--")
        for file in model["files"]:
            path = Path(
                hf_hub_download(
                    repo_id=model["repository"],
                    revision=model["revision"],
                    filename=file["path"],
                    local_dir=directory,
                )
            )
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != file["sha256"] or path.stat().st_size != file["bytes"]:
                raise ValueError("Model verification failed: " + file["path"])
        print("Verified " + model["repository"], flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
