import importlib.util, json, os, sys, tempfile, unittest, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from openpyxl import load_workbook
from pypdf import PdfWriter, PdfReader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server/pdf-to-excel"))
from convert import (
    convert,
    ConversionError,
    pages_for,
    clean,
    table_from_pdf,
    write_workbook,
)
from fixtures import generate
from text_tables import aligned_tables


class ConversionTests(unittest.TestCase):
    def test_scanned_borderless_table_retains_each_value(self):
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        import pypdfium2 as pdfium

        expected = [
            ["Item", "Quantity", "Price"],
            ["Apples", "12", "19.50"],
            ["Pears", "24", "28.75"],
            ["Oranges", "36", "39.25"],
            ["Lemons", "48", "49.00"],
        ]
        original = self.root / "borderless-scan-source.pdf"
        pdf = canvas.Canvas(str(original), pagesize=(595, 842))
        pdf.setFont("Helvetica", 20)
        for row, values in enumerate(expected):
            for x, value in zip((60, 250, 420), values):
                pdf.drawString(x, 720 - row * 56, value)
        pdf.save()
        document = pdfium.PdfDocument(original)
        page = document[0]
        bitmap = page.render(scale=2)
        raster = bitmap.to_pil().copy()
        bitmap.close()
        page.close()
        document.close()
        source = self.root / "borderless-scan.pdf"
        pdf = canvas.Canvas(str(source), pagesize=(595, 842))
        pdf.drawImage(ImageReader(raster), 0, 0, width=595, height=842)
        pdf.save()
        result, book, _ = self.run_case("borderless-scan")
        self.assertEqual(result["tables"], 1)
        self.assertEqual(result["ocrPages"], [1])
        self.assertEqual([list(row) for row in book.active.values], expected)
        self.assertFalse(book.active.merged_cells.ranges)
        book.close()

    def test_empty_user_password_is_readable_but_password_required_is_not(self):
        writer = PdfWriter(clone_from=self.root / "ruled.pdf")
        writer.encrypt(user_password="", owner_password="synthetic-owner")
        writer.write(self.root / "owner-protected.pdf")
        _, book, _ = self.run_case("owner-protected")
        expected = next(x["cells"] for x in self.expected if x["id"] == "ruled")
        self.assertEqual([list(row) for row in book.active.values], expected)
        book.close()
        with self.assertRaisesRegex(ConversionError, "Unlock"):
            self.run_case("encrypted")

    def test_visible_crop_controls_page_budget(self):
        from pypdf.generic import RectangleObject
        from types import SimpleNamespace
        from convert import visible_area

        writer = PdfWriter(clone_from=self.root / "ruled.pdf")
        page = writer.pages[0]
        original = tuple(page.mediabox)
        page.mediabox = RectangleObject((0, 0, 10000, 10000))
        page.cropbox = RectangleObject(original)
        writer.write(self.root / "large-media-small-crop.pdf")
        _, book, _ = self.run_case("large-media-small-crop")
        expected = next(x["cells"] for x in self.expected if x["id"] == "ruled")
        self.assertEqual([list(row) for row in book.active.values], expected)
        book.close()
        page.cropbox = page.mediabox
        writer.write(self.root / "large-visible-page.pdf")
        with self.assertRaisesRegex(ConversionError, "dimensions"):
            self.run_case("large-visible-page")
        for crop in [(20, 20, 10, 10), (500, 500, 600, 600)]:
            with self.subTest(crop=crop), self.assertRaises(ConversionError):
                visible_area(
                    SimpleNamespace(bbox=(0, 0, 100, 100), cropbox=crop, height=100)
                )

    def test_background_rectangles_are_not_merged_cell_separators(self):
        from reportlab.pdfgen import canvas

        source = self.root / "background-merges.pdf"
        pdf = canvas.Canvas(str(source), pagesize=(420, 792))
        pdf.setFillGray(0.8)
        # Same-colour paint rectangles have invisible adjoining edges.
        for x, y, width in (
            (50, 676, 100),
            (50, 652, 100),
            (150, 676, 100),
            (250, 676, 100),
        ):
            pdf.rect(x, y, width, 24, fill=1, stroke=0)
        pdf.setStrokeGray(0)
        pdf.setLineWidth(1)
        pdf.rect(50, 604, 300, 96, fill=0, stroke=1)
        pdf.line(150, 604, 150, 700)
        pdf.line(250, 604, 250, 676)
        pdf.line(150, 676, 350, 676)
        for y in (652, 628):
            pdf.line(50, y, 350, y)
        pdf.setFillGray(0)
        pdf.setFont("Helvetica", 10)
        for x, y, value in (
            (55, 670, "Group"),
            (155, 686, "Statistics"),
            (155, 662, "Code"),
            (255, 662, "Rate"),
            (55, 638, "First"),
            (155, 638, "00123"),
            (255, 638, "45%"),
            (55, 614, "Second"),
            (155, 614, "00456"),
            (255, 614, "67%"),
        ):
            pdf.drawString(x, y, value)
        pdf.save()
        output = self.root / "background-merges.xlsx"
        convert(source, output, {})
        book = load_workbook(output)
        sheet = book.worksheets[0]
        self.assertEqual(set(map(str, sheet.merged_cells.ranges)), {"A1:A2", "B1:C1"})
        self.assertEqual(sheet["B3"].value, "00123")
        self.assertEqual(sheet["B4"].value, "00456")
        book.close()

    def test_visible_crop_and_offset_origin_do_not_export_hidden_tables(self):
        from reportlab.pdfgen import canvas
        from pypdf.generic import RectangleObject

        original = self.root / "viewport-source.pdf"
        canvas_pdf = canvas.Canvas(str(original), pagesize=(1000, 500))
        canvas_pdf.setFont("FixtureCJK", 10)
        for left, label, code in ((40, "LEFT", "00123"), (540, "RIGHT", "00456")):
            for x in (left, left + 120, left + 240):
                canvas_pdf.line(x, 300, x, 420)
            for y in (300, 340, 380, 420):
                canvas_pdf.line(left, y, left + 240, y)
            for row, values in enumerate(
                (("Side", "Value"), (label, code), ("Range", "10–20"))
            ):
                for col, text in enumerate(values):
                    canvas_pdf.drawString(left + 5 + col * 120, 395 - row * 40, text)
        canvas_pdf.save()
        cases = (
            ("crop-left", None, (0, 0, 500, 500), {"LEFT"}, {"RIGHT", "00456"}),
            (
                "offset-right",
                (500, 0, 1000, 500),
                (500, 0, 1000, 500),
                {"RIGHT"},
                {"LEFT", "00123"},
            ),
            (
                "negative-origin",
                (-20, -30, 980, 470),
                (-20, -30, 980, 470),
                {"LEFT", "RIGHT"},
                set(),
            ),
        )
        for name, media, crop, visible, hidden in cases:
            with self.subTest(name=name):
                reader = PdfReader(original)
                page = reader.pages[0]
                if media:
                    page.mediabox = RectangleObject(media)
                page.cropbox = RectangleObject(crop)
                writer = PdfWriter()
                writer.add_page(page)
                writer.write(self.root / (name + ".pdf"))
                result, book, _ = self.run_case(name)
                values = {
                    c.value for sheet in book for row in sheet for c in row if c.value
                }
                self.assertEqual(result["tables"], len(visible))
                self.assertTrue(visible <= values)
                self.assertFalse(hidden & values)
                self.assertIn("10–20", values)

    def test_visible_grid_survives_an_empty_model_detection(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import pdfplumber
        from docling.datamodel.base_models import ConversionStatus
        from layout_tables import extract_layout_tables
        from convert import ruled_tables

        detector = SimpleNamespace(
            convert=lambda *args, **kwargs: SimpleNamespace(
                status=ConversionStatus.SUCCESS, document=SimpleNamespace(tables=[])
            )
        )
        source = self.root / "ruled.pdf"
        with pdfplumber.open(source) as document, patch(
            "layout_tables.converter_for", return_value=detector
        ):
            tables = extract_layout_tables(
                source, [0], "unused", document.pages, ruled_tables
            )[0]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["method"], "ruled-recovery")
        tables[0].update(page=1, index=1)
        output = self.root / "missed-detection.xlsx"
        write_workbook(tables, output, "tables")
        expected = next(x["cells"] for x in self.expected if x["id"] == "ruled")
        self.assertEqual(
            [list(row) for row in load_workbook(output).active.values], expected
        )

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.expected = generate(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, name, options=None):
        output = self.root / (name + "-output.xlsx")
        result = convert(self.root / (name + ".pdf"), output, options or {})
        return result, load_workbook(output), output

    def test_native_exact_text(self):
        for name in [
            "ruled",
            "borderless",
            "multiline",
            "chinese",
            "numbers",
            "landscape",
        ]:
            with self.subTest(name=name):
                _, book, _ = self.run_case(name)
                expected = next(x["cells"] for x in self.expected if x["id"] == name)
                self.assertEqual([list(r) for r in book.active.values], expected)

    def test_merged_structure(self):
        _, book, _ = self.run_case("merged")
        self.assertEqual([str(x) for x in book.active.merged_cells], ["A1:C1"])
        self.assertEqual(book.active["A1"].value, "Quarterly report")
        self.assertGreater(
            book.active.column_dimensions["B"].width,
            book.active.column_dimensions["A"].width,
        )

    def test_multipage_single_retains_both_headers_and_sources(self):
        result, book, _ = self.run_case("multipage", {"layout": "single"})
        self.assertEqual(result["tables"], 2)
        self.assertEqual(len(book.worksheets), 1)
        values = [c.value for row in book.active for c in row]
        self.assertEqual(values.count("Code"), 2)
        self.assertIn("Page 2 · Table 1", values)

    def test_page_selection(self):
        result, book, _ = self.run_case("multipage", {"pages": "2"})
        self.assertEqual(result["pages"], 1)
        self.assertEqual(book.active.title, "Page 2 Table 1")

    def test_formulas_never_execute_or_lose_precision(self):
        _, book, file = self.run_case("numbers")
        self.assertEqual(book.active["C2"].value, "=1+1")
        self.assertEqual(book.active["C2"].data_type, "s")
        self.assertEqual(book.active["A2"].value, "00123")
        self.assertEqual(book.active["B2"].value, "12345678901234567890")
        self.assertEqual(book.active["B3"].value, "1.234,50")
        with zipfile.ZipFile(file) as z:
            self.assertNotIn(b"<f>", z.read("xl/worksheets/sheet1.xml"))
            self.assertFalse(any("externalLink" in n for n in z.namelist()))

    def test_refusals(self):
        for name in ["no-table", "blank", "empty", "corrupted", "encrypted"]:
            with self.subTest(name=name), self.assertRaises(ConversionError):
                self.run_case(name)

    def test_scanned_and_mixed_never_silently_drop_without_ocr(self):
        for name in ["scan", "mixed"]:
            with self.subTest(name=name), self.assertRaisesRegex(
                ConversionError, "needs OCR"
            ):
                self.run_case(name, {"ocr": False})

    def test_range_boundary(self):
        self.assertEqual(pages_for("3,1-2,2", 3), [0, 1, 2])
        self.assertEqual(len(pages_for("all", 200)), 200)
        for value in ["0", "-1", "2-1", "1-999999999", "1,", "1.5", "a", None]:
            with self.subTest(value=value), self.assertRaises(ConversionError):
                pages_for(value, 5)

    def test_page_limit(self):
        w = PdfWriter()
        for _ in range(201):
            w.add_blank_page(width=595, height=842)
        w.write(self.root / "too-many.pdf")
        with self.assertRaisesRegex(ConversionError, "1–200"):
            self.run_case("too-many")

    def test_invalid_options(self):
        for options in [
            {"layout": "evil"},
            {"ocr": "true"},
            {"path": "elsewhere"},
            {"pages": "999"},
        ]:
            with self.subTest(options=options), self.assertRaises(ConversionError):
                self.run_case("ruled", options)

    def test_overlapping_cell_geometry_is_refused(self):
        from types import SimpleNamespace

        table = SimpleNamespace(
            cells=[(0, 0, 20, 20), (10, 0, 20, 10), (0, 10, 10, 20)],
            rows=[
                SimpleNamespace(cells=[(0, 0, 20, 20), (10, 0, 20, 10)]),
                SimpleNamespace(cells=[(0, 10, 10, 20), None]),
            ],
            extract=lambda **_: [["title", "other"], ["data", None]],
        )
        with self.assertRaisesRegex(ConversionError, "Overlapping"):
            table_from_pdf(table)

    def test_cell_length(self):
        with self.assertRaises(ConversionError):
            clean("a" * 32768)

    def test_long_cell_text_remains_visible_and_printable(self):
        text = (
            "A long description that must remain readable in the worksheet without hidden lines. "
            * 3
        )
        table = {
            "page": 1,
            "index": 1,
            "widths": [100, 100],
            "heights": [20, 20],
            "cells": [
                {"r": 0, "c": 0, "rs": 1, "cs": 1, "text": "Label"},
                {"r": 0, "c": 1, "rs": 1, "cs": 1, "text": "Description"},
                {"r": 1, "c": 0, "rs": 1, "cs": 1, "text": "00123"},
                {"r": 1, "c": 1, "rs": 1, "cs": 1, "text": text},
            ],
        }
        out = self.root / "readable.xlsx"
        write_workbook([table], out, "tables")
        book = load_workbook(out)
        self.assertEqual(book.active["B2"].value, text)
        self.assertGreater(book.active.row_dimensions[2].height, 100)
        self.assertLessEqual(book.active.row_dimensions[2].height, 409)
        self.assertEqual(book.active.page_setup.fitToWidth, 1)
        table["cells"][-1]["text"] = "UnbrokenVeryLongText" * 1000
        with self.assertRaisesRegex(ConversionError, "readable size"):
            write_workbook([table], out, "tables")

    def test_prose_is_not_split_into_invented_columns(self):
        from reportlab.pdfgen import canvas

        source = self.root / "prose.pdf"
        c = canvas.Canvas(str(source), pagesize=(595, 842))
        c.setFont("Helvetica", 11)
        lines = [
            "The annual report describes investment in education and public services.",
            "The committee reviewed funding for regional institutions and colleges.",
            "Many institutions provide training and support for their local communities.",
            "This paragraph contains ordinary sentences without any tabular columns.",
        ] * 4
        for i, line in enumerate(lines):
            c.drawString(50, 760 - i * 18, line)
        c.save()
        with self.assertRaisesRegex(ConversionError, "No tables"):
            convert(source, self.root / "prose.xlsx", {})

    def test_borderless_tables_separated_from_prose(self):
        from reportlab.pdfgen import canvas

        source = self.root / "separate-tables.pdf"
        c = canvas.Canvas(str(source), pagesize=(595, 842))
        c.setFont("Helvetica", 11)
        expected = [
            ["Code", "Description", "Amount"],
            ["0001", "First product", "123.45"],
            ["0002", "Second product", "-6.70"],
        ]
        for top in [700, 450]:
            c.drawString(
                50, top + 40, "An ordinary paragraph introduces the following table."
            )
            for r, row in enumerate(expected):
                for x, value in zip([50, 180, 370], row):
                    c.drawString(x, top - r * 24, value)
            c.drawString(
                50, top - 90, "A following sentence belongs outside the table."
            )
        c.save()
        out = self.root / "separate-tables.xlsx"
        result = convert(source, out, {})
        self.assertEqual(result["tables"], 2)
        for sheet in load_workbook(out):
            self.assertEqual([list(r) for r in sheet.values], expected)

    def test_inferred_columns_cannot_cut_source_words(self):
        from types import SimpleNamespace

        words = []
        for row in range(3):
            for x, text, width in [
                (10, "An ordinary sentence", 130),
                (160, "with more prose", 100),
            ]:
                words.append(
                    {
                        "x0": x,
                        "x1": x + width,
                        "top": row * 20,
                        "bottom": row * 20 + 10,
                        "text": text,
                    }
                )
        # One unusually long cell overlaps the next column, so no guessed split is allowed.
        words[2]["x1"] = 180
        page = SimpleNamespace(extract_words=lambda **_: words)
        self.assertEqual(aligned_tables(page), [])

    def test_missing_page_warning(self):
        w = PdfWriter()
        w.add_page(PdfReader(self.root / "ruled.pdf").pages[0])
        w.add_blank_page(width=595, height=842)
        w.write(self.root / "partial.pdf")
        result, _, _ = self.run_case("partial")
        self.assertEqual(result["missingPages"], [2])
        self.assertTrue(any("pages: 2" in s for s in result["warnings"]))

    def test_rotated_native_exact_without_stirling(self):
        from unittest.mock import patch

        expected = next(x["cells"] for x in self.expected if x["id"] == "rotated")
        with (
            patch.dict(os.environ, {"STIRLING_URL": ""}),
            patch(
                "convert.stirling_tables",
                side_effect=AssertionError("Native rotation must not call Stirling"),
            ) as fallback,
        ):
            _, book, _ = self.run_case("rotated")
        try:
            self.assertEqual([list(r) for r in book.active.values], expected)
            fallback.assert_not_called()
        finally:
            book.close()

    @unittest.skipUnless(os.getenv("STIRLING_URL"), "Requires real Stirling service")
    def test_rotated_stirling_direct_exact(self):
        from unittest.mock import patch

        from convert import stirling_tables

        source = self.root / "rotated.pdf"
        self.assertEqual(PdfReader(source).pages[0].rotation, 90)
        expected = next(x["cells"] for x in self.expected if x["id"] == "rotated")
        # Exercise the actual HTTP/XLSX adapter directly. Never let local page
        # normalization turn a missing or broken external service into a pass.
        with patch(
            "source_rotation.prepared_rotation",
            side_effect=AssertionError("External integration cannot normalize locally"),
        ):
            tables = stirling_tables(source, 0)
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual(table["method"], "stirling")
        self.assertEqual(len(table["heights"]), len(expected))
        self.assertEqual(len(table["widths"]), len(expected[0]))
        self.assertEqual(
            sorted(table["cells"], key=lambda cell: (cell["r"], cell["c"])),
            [
                {"r": r, "c": c, "rs": 1, "cs": 1, "text": text}
                for r, row in enumerate(expected)
                for c, text in enumerate(row)
            ],
        )

    @unittest.skipUnless(
        importlib.util.find_spec("rapidocr_onnxruntime"), "Requires OCR dependencies"
    )
    def test_scan_and_mixed(self):
        for name in ["scan", "mixed"]:
            with self.subTest(name=name):
                result, book, _ = self.run_case(name)
                self.assertEqual(result["tables"], 2 if name == "mixed" else 1)
                self.assertEqual(
                    [list(r) for r in book.worksheets[-1].values],
                    self.expected[0]["cells"],
                )
                self.assertTrue(result["ocrPages"])

    @unittest.skipUnless(
        importlib.util.find_spec("rapidocr_onnxruntime"), "Requires OCR dependencies"
    )
    def test_scanned_merged_header(self):
        _, book, _ = self.run_case("scan-merged")
        self.assertEqual([str(m) for m in book.active.merged_cells], ["A1:C1"])
        self.assertEqual(book.active["A1"].value, "Quarterly report")
        self.assertEqual(book.active["A3"].value, "00123")

    def test_vertical_merged_cell(self):
        _, book, _ = self.run_case("rowspan")
        self.assertEqual([str(m) for m in book.active.merged_cells], ["A2:A3"])
        self.assertEqual(book.active["A2"].value, "00123")
        self.assertEqual(book.active["B3"].value, "Widget B")

    @unittest.skipUnless(
        importlib.util.find_spec("rapidocr_onnxruntime"), "Requires OCR dependencies"
    )
    def test_scanned_chinese_and_rowspan(self):
        _, book, _ = self.run_case("scan-chinese")
        self.assertEqual(
            [list(r) for r in book.active.values],
            next(x["cells"] for x in self.expected if x["id"] == "chinese"),
        )
        _, book, _ = self.run_case("scan-rowspan")
        self.assertEqual([str(m) for m in book.active.merged_cells], ["A2:A3"])

    def test_original_typographic_glyphs_and_identifiers(self):
        from reportlab.pdfgen import canvas

        file = self.root / "typography.pdf"
        c = canvas.Canvas(str(file), pagesize=(595, 842))
        values = [
            ["Range", "Quote", "Code"],
            ["10–20", "‘Alpha’", "00123"],
            ["30—40", "“Beta”", "99999999999999999999"],
        ]
        for x in (50, 200, 350, 550):
            c.line(x, 600, x, 720)
        for y in (600, 640, 680, 720):
            c.line(50, y, 550, y)
        c.setFont("FixtureCJK", 10)
        for r, row in enumerate(values):
            for col, value in enumerate(row):
                c.drawString((55, 205, 355)[col], 695 - r * 40, value)
        c.save()
        _, book, _ = self.run_case("typography")
        self.assertEqual([list(row) for row in book.active.values], values)

    def test_two_tables_with_vertical_and_horizontal_header_merges(self):
        from reportlab.pdfgen import canvas

        file = self.root / "complex-headers.pdf"
        c = canvas.Canvas(str(file), pagesize=(595, 842))
        for top in (720, 440):
            c.setFont("Helvetica", 10)
            for x in (50, 200, 500):
                c.line(x, top - 180, x, top)
            c.line(350, top - 180, 350, top - 30)
            c.line(200, top - 30, 500, top - 30)
            for offset in (0, 60, 100, 140, 180):
                c.line(50, top - offset, 500, top - offset)
            c.drawString(65, top - 35, "Identifier")
            c.drawString(290, top - 20, "Measures")
            c.drawString(235, top - 50, "2024")
            c.drawString(395, top - 50, "2025")
            for row in range(3):
                for x, value in ((65, f"ID-{row}"), (235, "00123"), (395, "12,345.67")):
                    c.drawString(x, top - 85 - row * 40, value)
        c.save()
        result, book, _ = self.run_case("complex-headers")
        self.assertEqual(result["tables"], 2)
        for sheet in book:
            self.assertEqual({str(m) for m in sheet.merged_cells}, {"A1:A2", "B1:C1"})
            self.assertEqual(sheet["B3"].value, "00123")
            self.assertEqual(sheet["C5"].value, "12,345.67")


if __name__ == "__main__":
    unittest.main(verbosity=2)

