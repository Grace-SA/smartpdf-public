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

    @unittest.skipUnless(os.getenv("STIRLING_URL"), "Requires real Stirling service")
    def test_rotated_stirling_exact(self):
        _, book, _ = self.run_case("rotated")
        self.assertEqual(
            [list(r) for r in book.active.values], self.expected[0]["cells"]
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
