import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest

import pdfplumber
from openpyxl import load_workbook
from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    NameObject,
    DictionaryObject,
    ArrayObject,
    NumberObject,
    FloatObject,
)
from reportlab.pdfbase.pdfmetrics import stringWidth

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import ruled_tables, write_workbook
from layout_typography import apply_source_typography


def fixture(size=3.6, spaced_name=False):
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(240, 180))
    for x in [20, 60, 170]:
        canvas.line(x, 60, x, 100)
    for y in [60, 80, 100]:
        canvas.line(20, y, 170, y)
    canvas.setFont("Times-Roman", size)
    for x, y, text in [
        (22, 90, "Code"),
        (62, 90, "Description"),
        (22, 70, "0012"),
        (62, 70, "First part"),
    ]:
        canvas.drawString(x, y, text)
    canvas.drawString(62, 65, "Second part")
    canvas.save()
    stream.seek(0)
    if spaced_name:
        writer = PdfWriter()
        writer.append_pages_from_reader(PdfReader(stream))
        for ref in writer.pages[0]["/Resources"]["/Font"].values():
            font = ref.get_object()
            if font.get("/BaseFont") == "/Times-Roman":
                font[NameObject("/BaseFont")] = NameObject("/Times New Roman")
                font[NameObject("/FirstChar")] = NumberObject(32)
                font[NameObject("/LastChar")] = NumberObject(126)
                font[NameObject("/Widths")] = ArrayObject(
                    [
                        FloatObject(stringWidth(chr(i), "Times-Roman", 1000))
                        for i in range(32, 127)
                    ]
                )
                descriptor = DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/FontDescriptor"),
                        NameObject("/FontName"): NameObject("/Times New Roman"),
                        NameObject("/Flags"): NumberObject(34),
                        NameObject("/FontBBox"): ArrayObject(
                            [NumberObject(v) for v in [-168, -218, 1000, 898]]
                        ),
                        NameObject("/ItalicAngle"): NumberObject(0),
                        NameObject("/Ascent"): NumberObject(683),
                        NameObject("/Descent"): NumberObject(-217),
                        NameObject("/CapHeight"): NumberObject(662),
                        NameObject("/StemV"): NumberObject(84),
                    }
                )
                font[NameObject("/FontDescriptor")] = writer._add_object(descriptor)
        stream = io.BytesIO()
        writer.write(stream)
        stream.seek(0)
    document = pdfplumber.open(stream)
    table = ruled_tables(document.pages[0])[0]
    table["sourceGeometry"] = True
    return document, table


class SmallSourceFontTests(unittest.TestCase):
    def test_actual_pdf_with_spaced_standard_family_name_keeps_source_face(self):
        document, table = fixture(3.96, spaced_name=True)
        with document:
            self.assertIn(
                "Times New Roman", {c["fontname"] for c in document.pages[0].chars}
            )
            self.assertEqual(apply_source_typography(table, document.pages[0]), 4)
            self.assertTrue(
                all(c["fontName"] == "Times New Roman" for c in table["cells"])
            )
            self.assertTrue(
                all(abs(c["fontSize"] - 3.96) < 0.001 for c in table["cells"])
            )

    def test_verified_small_source_sizes_survive_workbook_without_row_inflation(self):
        for size in [3.6, 3.96]:
            document, table = fixture(size)
            with self.subTest(size=size), document:
                self.assertEqual(apply_source_typography(table, document.pages[0]), 4)
                table.update(page=1, index=1, fontSize=6)
                with tempfile.TemporaryDirectory() as folder:
                    output = Path(folder) / "small.xlsx"
                    write_workbook([table], output, "tables")
                    book = load_workbook(output)
                    self.assertEqual(book.active["A2"].value, "0012")
                    self.assertEqual(book.active["B2"].value, "First part\nSecond part")
                    self.assertAlmostEqual(book.active["A2"].font.sz, size)
                    self.assertAlmostEqual(book.active["B2"].font.sz, size)
                    self.assertEqual(book.active.row_dimensions[2].height, 20)
                    book.close()

    def test_unverified_grid_and_sub_three_point_sizes_keep_existing_fallback(self):
        for condition in ["model-geometry", "open-grid", "below-minimum"]:
            document, table = fixture(2.9 if condition == "below-minimum" else 3.6)
            with self.subTest(condition=condition), document:
                if condition == "model-geometry":
                    table.pop("sourceGeometry")
                elif condition == "open-grid":
                    table["closedGrid"] = False
                self.assertEqual(apply_source_typography(table, document.pages[0]), 0)
                self.assertTrue(all("sourceFont" not in c for c in table["cells"]))

    def test_small_type_never_rewrites_values_or_supplies_missing_numeric_glyphs(self):
        # Typography identifies a face from the same glyph multiset. It is not
        # a numeric-order validator: a permutation can share that face, but
        # the value must remain untouched and still fail separate text checks.
        for value, matched in [("0099", False), ("0021", True)]:
            document, table = fixture()
            with self.subTest(value=value), document:
                original = copy.deepcopy(table)
                cell = next(c for c in table["cells"] if c["text"] == "0012")
                cell["text"] = value
                self.assertEqual(
                    apply_source_typography(table, document.pages[0]),
                    4 if matched else 3,
                )
                self.assertEqual(cell.get("sourceFont", False), matched)
                self.assertEqual(cell["text"], value)
                self.assertEqual(table["widths"], original["widths"])
                self.assertEqual(table["heights"], original["heights"])
