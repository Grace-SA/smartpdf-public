"""Original offline integration regression; ready once caller routing is added."""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

for parent in Path(__file__).resolve().parents:
    if (parent / "server/pdf-to-excel").is_dir():
        sys.path.insert(0, str(parent / "server/pdf-to-excel"))
        sys.path.insert(0, str(parent / "scripts/pdf-to-excel"))
        break
from convert import ConversionError, convert
from test_source_hidden_ocr import scanned_table


class HiddenOCRIntegrationTests(unittest.TestCase):
    def test_ocr_adapter_uses_geometry_without_native_text_access(self):
        from layout_tables import adapt_table

        class GeometryOnlyPage:
            bbox = (0, 0, 300, 300)
            cropbox = None
            height = width = 300

            @property
            def chars(self):
                raise AssertionError("OCR adaptation must not read native glyphs")

            def extract_words(self, **kwargs):
                raise AssertionError("OCR adaptation must not read native words")

        bounds = {"l": 20, "t": 20, "r": 100, "b": 40, "coord_origin": "TOPLEFT"}
        item = {
            "data": {
                "num_rows": 1,
                "num_cols": 1,
                "table_cells": [
                    {
                        "text": "Code",
                        "start_row_offset_idx": 0,
                        "start_col_offset_idx": 0,
                        "row_span": 1,
                        "col_span": 1,
                        "bbox": bounds,
                    }
                ],
            },
            "prov": [{"bbox": bounds}],
        }
        with patch(
            "layout_tables.source_cell_text",
            side_effect=AssertionError("Native text restoration called"),
        ) as restore:
            table = adapt_table(item, GeometryOnlyPage(), native_text=False)
        restore.assert_not_called()
        self.assertEqual(table["cells"][0]["text"], "Code")
        self.assertIsNone(table["cells"][0]["sourceTextCandidate"])
        with patch(
            "layout_tables.source_cell_text", return_value="native marker"
        ) as restore:
            native = adapt_table(item, GeometryOnlyPage())
        restore.assert_called_once()
        self.assertEqual(native["cells"][0]["text"], "native marker")
        self.assertEqual(native["cells"][0]["sourceTextCandidate"], [20, 20, 100, 40])

    def test_hidden_wrong_number_uses_visible_scan_or_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "hidden.pdf"
            source.write_bytes(scanned_table(True))
            target = Path(folder) / "out.xlsx"
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            with (
                patch(
                    "convert.apply_source_typography",
                    side_effect=AssertionError("Hidden fonts must not be reused"),
                ),
                patch(
                    "convert.control_rectangles",
                    side_effect=AssertionError("Hidden scan must not use native forms"),
                ),
                patch(
                    "source_context.page_context",
                    side_effect=AssertionError("Hidden text must not become context"),
                ),
            ):
                result = convert(source, target, {"ocr": True})
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertTrue(
                any("invisible OCR" in warning for warning in result["warnings"])
            )
            self.assertEqual(result["ocrPages"], [1])
            book = load_workbook(target)
            try:
                values = [cell.value for row in book.active for cell in row]
                self.assertEqual(
                    list(book.active.values),
                    [
                        ("Code", "Amount"),
                        ("123", "12.50"),
                        ("007", "18.00"),
                        ("321", "25.30"),
                        ("555", "10.00"),
                    ],
                )
                self.assertIn("12.50", values)
                self.assertNotIn("19.50", values)
                comments = [
                    cell.comment.text
                    for row in book.active
                    for cell in row
                    if cell.comment
                ]
                self.assertFalse(any("19.50" in comment for comment in comments))
            finally:
                book.close()
            rejected = Path(folder) / "rejected.xlsx"
            with self.assertRaisesRegex(ConversionError, "needs OCR"):
                convert(source, rejected, {"ocr": False})
            self.assertFalse(rejected.exists())

    @unittest.skipUnless(
        os.getenv("PDF_EXCEL_MODELS"), "Requires pinned offline layout models"
    )
    def test_borderless_hidden_layer_cannot_reenter_layout_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "hidden-borderless.pdf"
            source.write_bytes(scanned_table(True, ruled=False))
            target = Path(folder) / "out.xlsx"
            with patch(
                "convert.apply_source_typography",
                side_effect=AssertionError("No hidden typography"),
            ):
                result = convert(source, target, {"ocr": True})
            self.assertEqual(result["ocrPages"], [1])
            book = load_workbook(target)
            try:
                self.assertEqual(
                    list(book.active.values),
                    [
                        ("Code", "Amount"),
                        ("123", "12.50"),
                        ("007", "18.00"),
                        ("321", "25.30"),
                        ("555", "10.00"),
                    ],
                )
            finally:
                book.close()

    def test_hidden_native_case_cannot_reenter_ocr_layout_adapter(self):
        # The visual OCR result is synthetic here; classification, PDF handling,
        # layout adaptation and final workbook serialization are real.
        import copy
        import io
        from types import SimpleNamespace

        import convert as engine
        from docling.datamodel.base_models import ConversionStatus
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject

        reader = PdfReader(io.BytesIO(scanned_table(True, ruled=False)))
        page = reader.pages[0]
        stream = DecodedStreamObject()
        stream.set_data(page["/Contents"].get_data().replace(b"(Code)", b"(CODE)"))
        page[NameObject("/Contents")] = stream
        expected = [
            ["Code", "Amount"],
            ["123", "12.50"],
            ["007", "18.00"],
            ["321", "25.30"],
            ["555", "10.00"],
        ]
        cells = []
        for row, values in enumerate(expected):
            for col, text in enumerate(values):
                cells.append(
                    {
                        "text": text,
                        "start_row_offset_idx": row,
                        "start_col_offset_idx": col,
                        "row_span": 1,
                        "col_span": 1,
                        "bbox": {
                            "l": 110 + 150 * col,
                            "t": 108 + 40 * row,
                            "r": 200 + 150 * col,
                            "b": 124 + 40 * row,
                            "coord_origin": "TOPLEFT",
                        },
                    }
                )
        item = {
            "data": {"num_rows": 5, "num_cols": 2, "table_cells": cells},
            "prov": [
                {
                    "bbox": {
                        "l": 100,
                        "t": 100,
                        "r": 400,
                        "b": 300,
                        "coord_origin": "TOPLEFT",
                    }
                }
            ],
        }
        detected = SimpleNamespace(
            data=SimpleNamespace(num_rows=5, num_cols=2),
            model_dump=lambda: copy.deepcopy(item),
        )
        fake = SimpleNamespace(
            convert=lambda *a, **k: SimpleNamespace(
                status=ConversionStatus.SUCCESS,
                document=SimpleNamespace(tables=[detected]),
            )
        )
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "hidden.pdf", Path(folder) / "out.xlsx"
            writer = PdfWriter()
            writer.add_page(page)
            writer.write(source)
            with (
                patch.dict(os.environ, {"PDF_EXCEL_MODELS": "mock-models"}),
                patch.object(
                    engine, "extract_layout_tables", return_value={}
                ) as native,
                patch.object(engine, "scan_tables", return_value=[]),
                patch.object(engine, "_ocr", object()),
                patch("ocr_layout.scan_converter", return_value=fake),
            ):
                result = convert(source, target, {"ocr": True})
            self.assertEqual(native.call_args.args[1], [])
            self.assertEqual(result["ocrPages"], [1])
            book = load_workbook(target)
            try:
                self.assertEqual([list(row) for row in book.active.values], expected)
            finally:
                book.close()

    def test_selected_native_page_ignores_unselected_hidden_page_and_late_refusal(self):
        import io

        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas

        native = io.BytesIO()
        pdf = canvas.Canvas(native, pagesize=(300, 300))
        for x in (30, 150, 270):
            pdf.line(x, 130, x, 250)
        for y in (130, 170, 210, 250):
            pdf.line(30, y, 270, y)
        expected = [("Code", "Value"), ("001", "12.50"), ("002", "20.00")]
        for r, row in enumerate(expected):
            for col, value in enumerate(row):
                pdf.drawString(35 + 120 * col, 225 - 40 * r, value)
        pdf.save()
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(native.getvalue())).pages[0])
        writer.add_page(PdfReader(io.BytesIO(scanned_table(True))).pages[0])
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "mixed.pdf"
            writer.write(source)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            target = Path(folder) / "native.xlsx"
            with (
                patch.dict(os.environ, {"PDF_EXCEL_MODELS": ""}),
                patch(
                    "source_hidden_ocr.classify",
                    side_effect=AssertionError("Unselected page inspected"),
                ),
                patch(
                    "convert.scan_tables",
                    side_effect=AssertionError("Native selection must not OCR"),
                ),
            ):
                result = convert(source, target, {"pages": "1", "ocr": False})
            self.assertEqual(result["ocrPages"], [])
            book = load_workbook(target)
            try:
                self.assertEqual(list(book.active.values), expected)
            finally:
                book.close()
            # Even after extracting page 1, refusal on page 2 must not publish a
            # partial workbook or damage an existing user output.
            rejected = Path(folder) / "rejected.xlsx"
            preserved = Path(folder) / "existing.xlsx"
            preserved.write_bytes(b"existing user output")
            with patch.dict(os.environ, {"PDF_EXCEL_MODELS": ""}):
                for output in (rejected, preserved):
                    with self.assertRaisesRegex(ConversionError, "Page 2 needs OCR"):
                        convert(source, output, {"ocr": False})
            self.assertFalse(rejected.exists())
            self.assertEqual(preserved.read_bytes(), b"existing user output")
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

            # In a mixed conversion, only the native page may be submitted to
            # native model extraction. The hidden page must still use real OCR.
            import convert as engine

            calls = []

            def native_only(path, indices, models, pages, extractor):
                calls.append(list(indices))
                self.assertEqual(indices, [0])
                return {index: engine.native_tables(pages[index]) for index in indices}

            mixed_target = Path(folder) / "mixed.xlsx"
            with (
                patch.dict(os.environ, {"PDF_EXCEL_MODELS": "partition-spy"}),
                patch.object(engine, "extract_layout_tables", side_effect=native_only),
            ):
                result = convert(source, mixed_target, {"ocr": True})
            self.assertEqual(calls, [[0]])
            self.assertEqual(result["ocrPages"], [2])
            book = load_workbook(mixed_target)
            try:
                self.assertEqual(len(book.worksheets), 2)
                self.assertEqual(list(book.worksheets[0].values), expected)
                self.assertEqual(book.worksheets[1]["B2"].value, "12.50")
                self.assertNotIn(
                    "19.50", [cell.value for row in book.worksheets[1] for cell in row]
                )
            finally:
                book.close()

    def test_hidden_scan_with_empty_user_password(self):
        import io

        from pypdf import PdfReader, PdfWriter

        with tempfile.TemporaryDirectory() as folder:
            source, target = (
                Path(folder) / "owner-protected.pdf",
                Path(folder) / "out.xlsx",
            )
            writer = PdfWriter()
            writer.add_page(PdfReader(io.BytesIO(scanned_table(True))).pages[0])
            writer.encrypt(user_password="", owner_password="synthetic-owner")
            writer.write(source)
            result = convert(source, target, {"ocr": True})
            self.assertEqual(result["ocrPages"], [1])
            book = load_workbook(target)
            try:
                self.assertEqual(book.active["B2"].value, "12.50")
            finally:
                book.close()
            writer.encrypt(
                user_password="synthetic-user", owner_password="synthetic-owner"
            )
            writer.write(source)
            protected_target = Path(folder) / "protected.xlsx"
            with self.assertRaisesRegex(ConversionError, "Unlock"):
                convert(source, protected_target, {"ocr": True})
            self.assertFalse(protected_target.exists())


if __name__ == "__main__":
    unittest.main()
