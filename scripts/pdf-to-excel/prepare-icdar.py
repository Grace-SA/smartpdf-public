"""Download a fixed publicly annotated research corpus; never put inputs in Git.

Usage: python prepare-icdar.py /local/research-directory [--manifest manifest.json]
Then run benchmark.py and evaluate-cells.py on that directory. Annotations are
used only by the separate scorer, never provided to the conversion process.
"""

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

MANIFEST = Path(__file__).with_name("icdar-public-manifest.json")


def verified_download(url, output, expected_blob):
    if output.exists():
        if output.stat().st_size > 30 * 1024 * 1024:
            raise ValueError("Public fixture exceeds download budget")
        data = output.read_bytes()
    else:
        request = urllib.request.Request(
            url, headers={"User-Agent": "SmartPDF-public-evaluation"}
        )
        with urllib.request.urlopen(request, timeout=40) as response:
            data = response.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024:
        raise ValueError("Public fixture exceeds download budget")
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if digest != expected_blob:
        raise ValueError(f"Pinned fixture checksum mismatch: {output.name}")
    if not output.exists():
        output.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def prepare(root, manifest_path=None):
    manifest = json.loads(Path(manifest_path or MANIFEST).read_text())
    if manifest["repository"] != "camelot-dev/camelot" or not re.fullmatch(
        r"[a-f0-9]{40}", manifest["commit"]
    ):
        raise ValueError("Unsupported public reference repository")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Public fixture selection must be nonempty")
    seen = set()
    for item in files:
        name = item["id"]
        if not isinstance(name, str) or not re.fullmatch(r"(?:eu|us)-\d{3}", name):
            raise ValueError("Invalid public fixture ID")
        if name in seen:
            raise ValueError("Duplicate public fixture ID")
        seen.add(name)
        expected_base = f"tests/files/tabula/icdar2013-dataset/competition-dataset-{name[:2]}/{name}"
        if (
            item["pdf"]["path"] != expected_base + ".pdf"
            or item["reference"]["path"] != expected_base + "-str.xml"
        ):
            raise ValueError("Unexpected public fixture path")
        for kind in ("pdf", "reference"):
            digest = item[kind].get("gitBlobSha1")
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{40}", digest):
                raise ValueError("Invalid public fixture blob identity")
    corpus, references = root / "corpus", root / "references"
    corpus.mkdir(parents=True, exist_ok=True)
    references.mkdir(exist_ok=True)
    rows = []
    base = f"https://raw.githubusercontent.com/{manifest['repository']}/{manifest['commit']}/"
    for item in files:
        name = item["id"]
        pdf_hash = verified_download(
            base + item["pdf"]["path"],
            corpus / (name + ".pdf"),
            item["pdf"]["gitBlobSha1"],
        )
        ref_hash = verified_download(
            base + item["reference"]["path"],
            references / (name + "-str.xml"),
            item["reference"]["gitBlobSha1"],
        )
        rows.append(
            {
                "id": name,
                "file": name + ".pdf",
                "sha256": pdf_hash,
                "referenceSha256": ref_hash,
                "repository": manifest["repository"],
                "commit": manifest["commit"],
                "path": item["pdf"]["path"],
                "license_review": "Public research fixture; no redistribution approved",
            }
        )
    (corpus / "manifest.json").write_text(json.dumps(rows, indent=2) + "\n")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps({"prepared": len(prepare(args.root, args.manifest))}))
