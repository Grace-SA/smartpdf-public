"""Synthetic conversion checks: values, mark ambiguity, combined sheets and rules."""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from unittest.mock import patch
from openpyxl import load_workbook
from reportlab.pdfgen import canvas
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import convert, write_workbook, ConversionError
from layout_forms import recover
from test_forms import fixture


def form_pages(path, pages=2, ambiguous=False, decoration=False):
    p = canvas.Canvas(str(path), pagesize=(400, 400))
    for page in range(pages):
        p.setFont("Helvetica", 10)
        p.drawString(30, 370, f"Application {page+1}")
        for i in range(6):
            y = 340 - i * 25
            p.rect(30, y, 9, 9)
            p.drawString(45, y, f"Choice {i+1}")
            if i % 2 == 0:
                p.line(30, y, 39, y + 9)
                if not ambiguous:
                    p.line(30, y + 9, 39, y)
        for y, value in [(160, "00017"), (140, "12345678901234567890"), (120, "=1+1")]:
            p.drawString(30, y, value)
        p.drawString(30, 90, "________")
        if decoration:
            p.rect(
                30,
                88.5,
                p.stringWidth("________", "Helvetica", 10),
                0.5,
                stroke=0,
                fill=1,
            )
        p.showPage()
    p.save()


class FormConversionTests(unittest.TestCase):
    def test_real_conversion_all_layouts_preserve_literals_and_every_mark(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "form.pdf"
            form_pages(source)
            for layout in ["tables", "single"]:
                with self.subTest(layout=layout):
                    out = Path(td) / f"{layout}.xlsx"
                    result = convert(source, out, dict(layout=layout, ocr=False))
                    self.assertEqual((result["forms"], result["missingPages"]), (2, []))
                    book = load_workbook(out)
                    self.assertEqual(
                        len(book.worksheets), 1 if layout == "single" else 2
                    )
                    values = [
                        c.value
                        for s in book
                        for row in s
                        for c in row
                        if c.value is not None
                    ]
                    for text in ["00017", "12345678901234567890", "=1+1", "________"]:
                        self.assertEqual(values.count(text), 2)
                    self.assertEqual((values.count("☒"), values.count("☐")), (6, 6))
                    self.assertTrue(
                        all(c.data_type != "f" for s in book for row in s for c in row)
                    )
                    self.assertEqual(result["preview"][0]["kind"], "form")
                    self.assertIn("Application 1", str(result["preview"][0]["values"]))
                    self.assertTrue(
                        all(
                            r.height > 0
                            for s in book
                            for r in s.row_dimensions.values()
                        )
                    )

    def test_ambiguous_checkbox_refuses_whole_document(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "ambiguous.pdf"
            form_pages(source, ambiguous=True)
            out = Path(td) / "out.xlsx"
            with self.assertRaisesRegex(ConversionError, "ambiguous marks"):
                convert(source, out, dict(ocr=False))
            self.assertFalse(out.exists())

    def test_underlines_only_become_drawing_when_source_rule_overprints_them(self):
        with tempfile.TemporaryDirectory() as td:
            for decorated in [False, True]:
                source = Path(td) / f"{decorated}.pdf"
                form_pages(source, pages=1, decoration=decorated)
                with pdfplumber.open(source) as pdf:
                    t = recover(pdf.pages[0])
                self.assertIsNotNone(t)
                self.assertEqual(len(t["decorations"]), int(decorated))
                self.assertEqual(
                    sum(c["text"] == "________" for c in t["cells"]), int(not decorated)
                )
                occupied = set()
                for c in t["cells"]:
                    slots = {
                        (r, col)
                        for r in range(c["r"], c["r"] + c["rs"])
                        for col in range(c["c"], c["c"] + c["cs"])
                    }
                    self.assertFalse(occupied & slots)
                    occupied.update(slots)

    def test_shared_sheet_keeps_readable_table_spans_and_form_rule_offsets(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "form.pdf"
            form_pages(source, pages=1, decoration=True)
            with pdfplumber.open(source) as pdf:
                form = recover(pdf.pages[0])
            form.update(page=2, index=1)
            table = dict(
                page=1,
                index=1,
                widths=[70, 80],
                heights=[25, 25],
                cells=[
                    dict(r=0, c=0, rs=1, cs=2, text="Grouped heading"),
                    dict(r=1, c=0, rs=1, cs=1, text="001"),
                    dict(r=1, c=1, rs=1, cs=1, text="002"),
                ],
            )
            out = Path(td) / "combined.xlsx"
            write_workbook([table, form], out, "single")
            book = load_workbook(out)
            sheet = book.active
            values = [c.value for row in sheet for c in row if c.value]
            self.assertTrue(
                all(
                    v in values
                    for v in ["Grouped heading", "001", "002", "Application 1"]
                )
            )
            self.assertEqual(sheet["A2"].value, "Grouped heading")
            header = next(m for m in sheet.merged_cells.ranges if m.min_row == 2)
            self.assertGreater(header.max_col, 50)
            self.assertEqual(
                len({d.width for d in sheet.column_dimensions.values()}), 1
            )
            with ZipFile(out) as z:
                root = ET.fromstring(z.read("xl/drawings/form-rules-1.xml"))
                start = next(e for e in root.iter() if e.tag.endswith("}from"))
                row = int(next(e.text for e in start if e.tag.endswith("}row")))
                self.assertGreater(row, 5)
            self.assertEqual(table["widths"], [70, 80])

    def test_rule_placements_do_not_collide_in_single_sheet(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "forms.pdf"
            form_pages(source, decoration=True)
            out = Path(td) / "single.xlsx"
            convert(source, out, dict(layout="single", ocr=False))
            with ZipFile(out) as z:
                drawings = [n for n in z.namelist() if n.startswith("xl/drawings/")]
                self.assertEqual(len(drawings), 1)
                root = ET.fromstring(z.read(drawings[0]))
                rows = []
                for start in (e for e in root.iter() if e.tag.endswith("}from")):
                    rows.append(
                        int(next(e.text for e in start if e.tag.endswith("}row")))
                    )
                self.assertEqual(len(rows), 2)
                self.assertGreater(rows[1], rows[0])
                ids = [e.get("id") for e in root.iter() if e.tag.endswith("}cNvPr")]
                self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
