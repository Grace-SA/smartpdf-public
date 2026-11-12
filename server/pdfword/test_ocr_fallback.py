import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from ocr import OCR, normalize
from model import Rejected


class FallbackTests(unittest.TestCase):
    def test_u2_other_preserves_text_but_not_unreadable_or_embedded_tables(self):
        row = dict(label="other", bbox=[10, 20, 900, 80], content="Synthetic heading")
        block = normalize([row], 612, 792, "u2")[0]
        self.assertEqual(
            (block["kind"], block["text"]), ("paragraph", "Synthetic heading")
        )
        for value in (
            "",
            "[unreadable]",
            "[image]",
            "<table><tr><td>123</td></tr></table>",
        ):
            with self.assertRaises(Rejected):
                normalize([{**row, "content": value}], 612, 792, "u2")
        with self.assertRaises(Rejected):
            normalize([row], 612, 792, "oxr")

    def test_retry_uses_original_pixels_and_shared_budget(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, PDFWORD_MODEL_ROOT=tmp, PDFWORD_OCR_PYTHON="python"
        ):
            root = Path(tmp)
            (root / "u2").mkdir()
            image = root / "input.png"
            image.write_bytes(b"original")
            ocr = OCR(root)
            calls = []

            def recognize(path, width, height, engine, budget):
                calls.append((engine, budget))
                self.assertEqual(path.read_bytes(), b"original")
                if engine == "oxr":
                    path.write_bytes(b"changed")
                    raise Rejected("Incomplete table grid")
                return [{"kind": "paragraph", "text": "recovered"}]

            with patch.object(ocr, "_recognize", side_effect=recognize):
                self.assertEqual(ocr.recognize(image, 612, 792)[0]["text"], "recovered")
            self.assertEqual(ocr.last_engine, "u2-fallback")
            self.assertEqual(calls[0], ("oxr", 120))
            self.assertLessEqual(calls[1][1], 180)
            self.assertFalse((root / "ocr-original.png").exists())

    def test_cancel_does_not_launch_another_engine(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, PDFWORD_MODEL_ROOT=tmp, PDFWORD_OCR_PYTHON="python"
        ):
            root = Path(tmp)
            (root / "u2").mkdir()
            image = root / "input.png"
            image.write_bytes(b"original")
            cancel = root / "cancel"
            ocr = OCR(root, cancel)

            def recognize(*args):
                cancel.touch()
                raise Rejected("Conversion cancelled.")

            with patch.object(ocr, "_recognize", side_effect=recognize) as call:
                with self.assertRaises(Rejected):
                    ocr.recognize(image, 612, 792)
                self.assertEqual(call.call_count, 1)
