import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "prepare_icdar", Path(__file__).with_name("prepare-icdar.py")
)
prepare_icdar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_icdar)


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class PublicCorpusTests(unittest.TestCase):
    def test_fixed_manifest_has_twelve_distinct_pinned_documents(self):
        data = json.loads(prepare_icdar.MANIFEST.read_text())
        self.assertEqual(
            [x["id"] for x in data["files"]],
            [f"{region}-{i:03}" for region in ("eu", "us") for i in range(1, 7)],
        )
        for item in data["files"]:
            for kind in ("pdf", "reference"):
                self.assertRegex(item[kind]["gitBlobSha1"], r"^[0-9a-f]{40}$")

    def test_verified_cache_never_needs_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.pdf"
            data = b"%PDF- synthetic fixture"
            path.write_bytes(data)
            with patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("cache must not fetch"),
            ):
                self.assertEqual(
                    prepare_icdar.verified_download(
                        "https://example.invalid", path, blob(data)
                    ),
                    hashlib.sha256(data).hexdigest(),
                )
            with self.assertRaisesRegex(ValueError, "checksum"):
                prepare_icdar.verified_download(
                    "https://example.invalid", path, "0" * 40
                )
            self.assertEqual(path.read_bytes(), data)

    def test_oversized_cache_is_rejected_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.pdf"
            with path.open("wb") as stream:
                stream.truncate(30 * 1024 * 1024 + 1)
            with (
                patch.object(
                    Path,
                    "read_bytes",
                    side_effect=AssertionError("must check size first"),
                ),
                self.assertRaisesRegex(ValueError, "budget"),
            ):
                prepare_icdar.verified_download(
                    "https://example.invalid", path, "0" * 40
                )

    def test_bad_download_never_becomes_a_cached_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.pdf"
            with (
                patch(
                    "urllib.request.urlopen", return_value=io.BytesIO(b"wrong content")
                ),
                self.assertRaisesRegex(ValueError, "checksum"),
            ):
                prepare_icdar.verified_download(
                    "https://example.invalid", path, "0" * 40
                )
            self.assertFalse(path.exists())

    def test_prepare_separates_annotations_from_conversion_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = json.loads(prepare_icdar.MANIFEST.read_text())
            data["files"] = data["files"][:1]
            pdf, reference = b"%PDF- synthetic", b"<document/>"
            data["files"][0]["pdf"]["gitBlobSha1"] = blob(pdf)
            data["files"][0]["reference"]["gitBlobSha1"] = blob(reference)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(data))
            with (
                patch.object(prepare_icdar, "MANIFEST", manifest),
                patch(
                    "urllib.request.urlopen",
                    side_effect=[io.BytesIO(pdf), io.BytesIO(reference)],
                ),
            ):
                rows = prepare_icdar.prepare(root / "run")
            self.assertEqual(rows[0]["file"], "eu-001.pdf")
            self.assertEqual(
                (root / "run/references/eu-001-str.xml").read_bytes(), reference
            )
            self.assertFalse((root / "run/corpus/eu-001-str.xml").exists())


if __name__ == "__main__":
    unittest.main()
