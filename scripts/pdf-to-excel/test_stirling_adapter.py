"""Offline adapter contract tests; no server, downloads, or model inference."""

import io
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from openpyxl import Workbook, load_workbook
from pypdf import PdfReader
from reportlab.pdfgen import canvas

for parent in Path(__file__).resolve().parents:
    if (parent / "server/pdf-to-excel").is_dir():
        sys.path.insert(0, str(parent / "server/pdf-to-excel"))
        break

from convert import ConversionError, stirling_tables, write_workbook


class Response(io.BytesIO):
    status = 200


def workbook_bytes(book):
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def single_cell(value, fmt="General", data_type=None):
    book = Workbook()
    cell = book.active.cell(1, 1, value)
    cell.number_format = fmt
    if data_type:
        cell.data_type = data_type
    return workbook_bytes(book)


class StirlingAdapterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / "source.pdf"
        pdf = canvas.Canvas(str(self.source), pagesize=(300, 200))
        pdf.drawString(20, 150, "Page one")
        pdf.showPage()
        pdf.drawString(20, 150, "Selected page two")
        pdf.save()

    def run_adapter(self, data):
        # All network calls are intercepted. Also isolate any inherited API key.
        with (
            patch.dict(
                os.environ,
                {"STIRLING_URL": "http://127.0.0.1:18765/", "STIRLING_API_KEY": ""},
            ),
            patch("urllib.request.urlopen", return_value=Response(data)) as request,
        ):
            result = stirling_tables(self.source, 1)
        request.assert_called_once()
        args, kwargs = request.call_args
        req = args[0]
        self.assertEqual(req.full_url, "http://127.0.0.1:18765/api/v1/convert/pdf/xlsx")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(kwargs, {"timeout": 45})
        self.assertIsNone(req.get_header("X-api-key"))
        mime = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + req.get_header("Content-type") + "\r\n\r\n").encode()
            + req.data
        )
        parts = list(mime.iter_parts())
        self.assertEqual(
            [p.get_param("name", header="content-disposition") for p in parts],
            ["fileInput", "useStirlingOfficeConvert"],
        )
        self.assertEqual(parts[0].get_filename(), "input.pdf")
        self.assertEqual(parts[0].get_content_type(), "application/pdf")
        selected = PdfReader(io.BytesIO(parts[0].get_payload(decode=True)))
        self.assertEqual(len(selected.pages), 1)
        self.assertIn("Selected page two", selected.pages[0].extract_text())
        self.assertNotIn("Page one", selected.pages[0].extract_text())
        self.assertEqual(parts[1].get_payload(decode=True), b"true")
        return result

    def test_seven_supported_literal_formats(self):
        cases = [
            ("001234", "General", "001234"),
            ("123456789012345678", "General", "123456789012345678"),
            (1.2, "0.00", "1.20"),
            (0.125, "0.0%", "12.5%"),
            (datetime(2024, 1, 2), r"mm\/dd\/yyyy", "01/02/2024"),
            (1234.5, '"$"#,##0.00', "$1,234.50"),
            (-12.3, "0.00;(0.00)", "(12.30)"),
        ]
        book = Workbook()
        for row, (value, fmt, _) in enumerate(cases, 1):
            cell = book.active.cell(row, 1, value)
            cell.number_format = fmt
        table = self.run_adapter(workbook_bytes(book))[0]
        self.assertEqual([c["text"] for c in table["cells"]], [x[2] for x in cases])

    def test_unknown_precision_and_ambiguous_zero_rejected(self):
        for value, fmt in [
            (2, "[Red]0"),
            (123456789012345678, "0"),
            (0, "0.00;(0.00)"),
            (0, "0.00;(0.00);0.0"),
            (-0.004, "0.00"),
        ]:
            with (
                self.subTest(value=value, fmt=fmt),
                self.assertRaisesRegex(ConversionError, "External workbook display"),
            ):
                self.run_adapter(single_cell(value, fmt))

    def test_parenthesized_numeric_zero_has_explicit_reason(self):
        with self.assertRaisesRegex(ConversionError, "Parenthesized zero"):
            self.run_adapter(single_cell(0, "0.0;(0.0)"))

    def test_strings_booleans_and_formula_text(self):
        for value, kind, expected in [
            ("001234", "s", "001234"),
            ("123456789012345678", "s", "123456789012345678"),
            ("=SUM(A1:A3)", "s", "=SUM(A1:A3)"),
            ("=SUM(A1:A3)", "f", "=SUM(A1:A3)"),
            (True, None, "TRUE"),
            (False, None, "FALSE"),
        ]:
            with self.subTest(value=value, kind=kind):
                result = self.run_adapter(single_cell(value, data_type=kind))
                self.assertEqual(result[0]["cells"][0]["text"], expected)

    def test_formula_is_literal_in_final_output(self):
        tables = self.run_adapter(single_cell("=1+1", data_type="f"))
        for table in tables:
            table.update(page=1, index=1)
        target = Path(self.folder.name) / "literal.xlsx"
        write_workbook(tables, target, "sheets")
        book = load_workbook(target)
        self.addCleanup(book.close)
        self.assertEqual(book.active["A1"].value, "=1+1")
        self.assertEqual(book.active["A1"].data_type, "s")
        with zipfile.ZipFile(target) as archive:
            for name in archive.namelist():
                self.assertFalse(name.startswith("xl/externalLinks/"))
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    root = ET.fromstring(archive.read(name))
                    self.assertFalse(
                        root.findall(
                            ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f"
                        )
                    )

    def test_original_nine_cell_fixture(self):
        book = Workbook()
        expected = [
            ["Code", "Product", "Amount"],
            ["00123", "Widget A", "1,234.50"],
            ["00987", "Widget B", "-12.00"],
        ]
        for row in expected:
            book.active.append(row)
        book.active["C2"] = 1234.5
        book.active["C2"].number_format = "#,##0.00"
        book.active["C3"] = -12
        book.active["C3"].number_format = "0.00"
        table = self.run_adapter(workbook_bytes(book))[0]
        self.assertEqual(
            [c["text"] for c in table["cells"]],
            [value for row in expected for value in row],
        )

    def test_numeric_and_literal_zero_distinct(self):
        for value, fmt, expected in [
            ("0", "0.0;(0.0)", "0"),
            ("(0.0)", "General", "(0.0)"),
            (0, "0.0", "0.0"),
        ]:
            with self.subTest(value=value):
                table = self.run_adapter(single_cell(value, fmt))[0]
                self.assertEqual(table["cells"][0]["text"], expected)

    def test_structure_merges_and_dimensions_unchanged(self):
        book = Workbook()
        sheet = book.active
        sheet["A1"] = "Title"
        sheet.merge_cells("A1:C1")
        sheet["A2"] = "Group"
        sheet.merge_cells("A2:A3")
        sheet["B2"] = 1.2
        sheet["B2"].number_format = "0.00"
        sheet["C3"] = "Tail"
        sheet.column_dimensions["A"].width = 20
        sheet.column_dimensions["B"].width = 10
        sheet.column_dimensions["C"].width = 15
        sheet.row_dimensions[1].height = 24
        second = book.create_sheet("Second")
        second["A1"] = "Other"
        tables = self.run_adapter(workbook_bytes(book))
        self.assertEqual(len(tables), 2)
        self.assertEqual(
            tables[0],
            {
                "widths": [140, 70, 105],
                "heights": [24, 20, 20],
                "method": "stirling",
                "cells": [
                    {"r": 0, "c": 0, "rs": 1, "cs": 3, "text": "Title"},
                    {"r": 1, "c": 0, "rs": 2, "cs": 1, "text": "Group"},
                    {"r": 1, "c": 1, "rs": 1, "cs": 1, "text": "1.20"},
                    {"r": 2, "c": 2, "rs": 1, "cs": 1, "text": "Tail"},
                ],
            },
        )
        self.assertEqual(
            tables[1]["cells"], [{"r": 0, "c": 0, "rs": 1, "cs": 1, "text": "Other"}]
        )


if __name__ == "__main__":
    unittest.main()
