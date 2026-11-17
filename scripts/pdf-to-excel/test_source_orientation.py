import copy
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pdfplumber
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from source_orientation import sideways_text, sideways_turn, upright_source
from convert import convert, ConversionError


class SourceOrientationTests(unittest.TestCase):
    def page(self, count=100, matrix=(0, 1, -1, 0, 0, 0)):
        return SimpleNamespace(
            rotation=0,
            width=300,
            height=400,
            chars=[
                dict(text="A", x0=10, x1=20, top=20, bottom=30, matrix=matrix)
                for _ in range(count)
            ],
        )

    def test_both_quarter_turns_require_sufficient_consistent_evidence(self):
        self.assertTrue(sideways_text(self.page()))
        self.assertTrue(sideways_text(self.page(matrix=(0, -1, 1, 0, 0, 0))))
        self.assertFalse(sideways_text(self.page(count=49)))
        page = self.page()
        page.chars[:5] = self.page(5, (1, 0, 0, 1, 0, 0)).chars
        self.assertTrue(sideways_text(page))
        page.chars[5] = self.page(1, (1, 0, 0, 1, 0, 0)).chars[0]
        self.assertFalse(sideways_text(page))
        page = self.page()
        page.chars[:50] = self.page(50, (0, -1, 1, 0, 0, 0)).chars
        self.assertFalse(sideways_text(page))

    def test_crop_and_invalid_or_skewed_matrices_abstain(self):
        for matrix in [
            None,
            (0, 1),
            (float("nan"), 1, -1, 0, 0, 0),
            ("0", 1, -1, 0, 0, 0),
            (0, 0, 0, 0, 0, 0),
            (0, 1, 1, 0, 0, 0),
            (0.2, 1, -1, 0.2, 0, 0),
        ]:
            with self.subTest(matrix=matrix):
                self.assertFalse(sideways_text(self.page(matrix=matrix)))
        page = self.page()
        page.cropbox = (30, 0, 300, 400)
        self.assertFalse(sideways_text(page))
        page = self.page()
        for ch in page.chars:
            ch["text"] = "."
        self.assertFalse(sideways_text(page))

    def source(self, root):
        source = root / "sideways.pdf"
        c = Canvas(str(source), pagesize=(400, 400))
        c.translate(300, 30)
        c.rotate(90)
        c.setFont("Helvetica", 10)
        c.drawString(0, 0, "ABCDEFGHIJ" * 6)
        c.save()
        return source

    def test_normalized_source_keeps_pixels_text_and_original_and_cleans_copy(self):
        import hashlib
        import pypdfium2 as pdfium
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = self.source(root)
            original = source.read_bytes()
            before = pdfium.PdfDocument(source)
            first = before[0]
            bitmap = first.render(scale=2, rotation=90)
            expected = bitmap.to_pil().copy()
            bitmap.close()
            first.close()
            before.close()
            with upright_source(source, [0], root) as (prepared, pages):
                self.assertNotEqual(source, prepared)
                self.assertEqual(pages, [1])
                self.assertEqual(PdfReader(prepared).pages[0].rotation, 0)
                with pdfplumber.open(prepared) as doc:
                    self.assertIsNone(sideways_turn(doc.pages[0]))
                    self.assertEqual(doc.pages[0].extract_text(), "ABCDEFGHIJ" * 6)
                after = pdfium.PdfDocument(prepared)
                page = after[0]
                bitmap = page.render(scale=2)
                actual = bitmap.to_pil().copy()
                bitmap.close()
                page.close()
                after.close()
                self.assertEqual(actual.size, expected.size)
                self.assertEqual(actual.tobytes(), expected.tobytes())
            self.assertFalse(prepared.exists())
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(list(root.glob(".pdf-excel-upright-*")), [])
            with self.assertRaisesRegex(RuntimeError, "consumer failed"):
                with upright_source(source, [0], root):
                    raise RuntimeError("consumer failed")
            self.assertEqual(list(root.glob(".pdf-excel-upright-*")), [])

    def test_only_selected_sideways_pages_are_normalized(self):
        from pypdf import PdfReader, PdfWriter

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = self.source(root)
            writer = PdfWriter()
            writer.add_page(PdfReader(source).pages[0])
            writer.add_page(PdfReader(source).pages[0])
            multi = root / "multi.pdf"
            writer.write(multi)
            with upright_source(multi, [], root) as (prepared, pages):
                self.assertEqual(prepared, multi)
                self.assertEqual(pages, [])
            with upright_source(multi, [1], root) as (prepared, pages):
                self.assertEqual(pages, [2])
                with pdfplumber.open(prepared) as doc:
                    self.assertTrue(sideways_text(doc.pages[0]))
                    self.assertFalse(sideways_text(doc.pages[1]))

    def test_conversion_models_receive_upright_text_without_server_dependency(self):
        table = dict(
            method="layout",
            widths=[80, 80],
            heights=[20, 20],
            cells=[
                dict(r=r, c=c, rs=1, cs=1, text=str(r * 2 + c))
                for r in range(2)
                for c in range(2)
            ],
        )
        sources = []

        def extract(source, indices, models, pages, ruled):
            sources.append(source)
            self.assertEqual(indices, [0])
            self.assertFalse(sideways_text(pages[0]))
            self.assertEqual(pages[0].extract_text(), "ABCDEFGHIJ" * 6)
            return {0: [copy.deepcopy(table)]}

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = self.source(root)
            with patch.dict(
                os.environ, {"PDF_EXCEL_MODELS": "synthetic-models", "STIRLING_URL": ""}
            ), patch("convert.extract_layout_tables", side_effect=extract), patch(
                "convert.stirling_tables"
            ) as server:
                result = convert(source, root / "output.xlsx", {})
                server.assert_not_called()
                self.assertEqual(result["tables"], 1)
                self.assertTrue(any("rotated upright" in w for w in result["warnings"]))
            self.assertEqual(len(sources), 1)
            self.assertFalse(sources[0].exists())

    def test_real_rotation_metadata_is_combined_with_native_text_direction(self):
        import pypdfium2 as pdfium
        from pypdf import PdfReader, PdfWriter

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = self.source(root)
            for rotation, turn in [(0, 90), (90, None), (180, 270), (270, None)]:
                with self.subTest(rotation=rotation):
                    writer = PdfWriter(clone_from=source)
                    writer.pages[0].rotate(rotation)
                    marked = root / f"marked-{rotation}.pdf"
                    writer.write(marked)
                    with pdfplumber.open(marked) as doc:
                        self.assertEqual(sideways_turn(doc.pages[0]), turn)
                    if turn is None:
                        continue
                    before = pdfium.PdfDocument(marked)
                    page = before[0]
                    bitmap = page.render(scale=2, rotation=turn)
                    expected = bitmap.to_pil().copy()
                    bitmap.close()
                    page.close()
                    before.close()
                    original = marked.read_bytes()
                    with upright_source(marked, [0], root) as (prepared, pages):
                        self.assertEqual(pages, [1])
                        self.assertEqual(PdfReader(prepared).pages[0].rotation, 0)
                        with pdfplumber.open(prepared) as doc:
                            self.assertIsNone(sideways_turn(doc.pages[0]))
                            self.assertEqual(
                                doc.pages[0].extract_text(), "ABCDEFGHIJ" * 6
                            )
                        after = pdfium.PdfDocument(prepared)
                        page = after[0]
                        bitmap = page.render(scale=2)
                        actual = bitmap.to_pil().copy()
                        bitmap.close()
                        page.close()
                        after.close()
                        self.assertEqual(expected.size, actual.size)
                        self.assertEqual(expected.tobytes(), actual.tobytes())
                    self.assertEqual(marked.read_bytes(), original)
