"""Prepare an offline, hash-pinned Java adapter from the approved core JAR."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

CORE_SHA256 = "370a4218624fa4b3cf5460c886f03de01bfcfd2d4893009202a81e53b5f3344d"


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def build(jar, destination, javac):
    jar, destination = Path(jar), Path(destination)
    if digest(jar) != CORE_SHA256:
        raise ValueError("Stirling core hash mismatch")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "lib").mkdir()
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            if name.startswith("BOOT-INF/lib/") and name.endswith(".jar"):
                target = destination / "lib" / Path(name).name
                with target.open("xb") as out:
                    out.write(archive.read(name))
    source = Path(__file__).with_name("StirlingBridge.java")
    subprocess.run([str(javac), "-cp", str(destination / "lib/*"),
                    "-d", str(destination), str(source)], check=True, timeout=60)
    manifest = dict(core_sha256=CORE_SHA256, version="0.2.2", source_sha256=digest(source),
                    files={str(p.relative_to(destination)): digest(p)
                           for p in sorted(destination.rglob("*")) if p.is_file()})
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jar", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--javac", required=True, type=Path)
    args = parser.parse_args()
    build(args.jar, args.destination, args.javac)
