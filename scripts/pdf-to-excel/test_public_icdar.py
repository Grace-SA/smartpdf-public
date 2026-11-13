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

    def test_next_manifest_preserves_preselected_ids_and_provenance_exclusions(self):
        data = json.loads(
            Path(__file__).with_name("icdar-next-public-manifest.json").read_text()
        )
        original = [f"{region}-{i:03}" for region in ("eu", "us") for i in range(7, 13)]
        missing = ["eu-009", "us-011"]
        self.assertEqual(data["preselection"]["originalSelection"], original)
        self.assertEqual(data["preselection"]["missingExactPairs"], missing)
        self.assertTrue(data["preselection"]["selectedBeforeQualityInspection"])
        self.assertEqual(
            [x["id"] for x in data["files"]], [x for x in original if x not in missing]
        )
        self.assertEqual(data["commit"], "92777b852e00933a5c4b9ba642601784604356cd")
        for item in data["files"]:
            for kind in ("pdf", "reference"):
                self.assertRegex(item[kind]["gitBlobSha1"], r"^[a-f0-9]{40}$")

    def test_explicit_manifest_selects_only_requested_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = json.loads(prepare_icdar.MANIFEST.read_text())
            data["files"] = data["files"][1:2]
            manifest = root / "explicit.json"
            manifest.write_text(json.dumps(data))
            with patch.object(
                prepare_icdar, "verified_download", return_value="a" * 64
            ) as fetch:
                rows = prepare_icdar.prepare(root / "run", manifest)
            self.assertEqual([row["id"] for row in rows], ["eu-002"])
            self.assertEqual(fetch.call_count, 2)
            self.assertTrue(
                all("eu-002" in call.args[0] for call in fetch.call_args_list)
            )

    def test_invalid_selections_fail_before_any_download_or_output(self):
        original = json.loads(prepare_icdar.MANIFEST.read_text())
        variants = []
        for change in (
            "empty",
            "duplicate",
            "late_bad_path",
            "late_bad_blob",
            "bad_id",
            "repository",
            "commit",
        ):
            data = json.loads(json.dumps(original))
            if change == "empty":
                data["files"] = []
            elif change == "duplicate":
                data["files"].append(data["files"][0])
            elif change == "late_bad_path":
                data["files"][-1]["pdf"]["path"] = "../outside.pdf"
            elif change == "late_bad_blob":
                data["files"][-1]["reference"]["gitBlobSha1"] = "invalid"
            elif change == "bad_id":
                data["files"][-1]["id"] = "../outside"
            elif change == "repository":
                data["repository"] = "other/repo"
            else:
                data["commit"] = "main"
            variants.append((change, data))
        for name, data in variants:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest = root / "input.json"
                manifest.write_text(json.dumps(data))
                with patch.object(prepare_icdar, "verified_download") as fetch:
                    with self.assertRaises(ValueError):
                        prepare_icdar.prepare(root / "run", manifest)
                    fetch.assert_not_called()
                self.assertFalse((root / "run").exists())

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
