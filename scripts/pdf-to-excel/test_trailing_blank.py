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
from pypdf.generic import RectangleObject

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import ruled_tables, table_from_pdf, write_workbook
from layout_trailing_blank import recover


def fixture(blank_middle=False, shifted=False, closed_rectangle=False):
    stream = io.BytesIO()
    width = 850 if shifted else 400
    offset = 420 if shifted else 0
    canvas = Canvas(stream, pagesize=(width, 240))
    canvas.setFont("Helvetica", 10)
    xs = [20 + offset, 180 + offset, 360 + offset]
    ys = [20, 50, 80, 110, 190]
    if closed_rectangle:
        canvas.rect(xs[0], 240 - ys[-1], xs[-1] - xs[0], ys[-1] - ys[0])
    for x in (xs[1:-1] if closed_rectangle else xs):
        canvas.line(x, 240 - ys[0], x, 240 - ys[-1])
    for y in (ys[1:-1] if closed_rectangle else ys):
        canvas.line(xs[0], 240 - y, xs[-1], 240 - y)
    data = [["Name", "Amount"], ["Item A", "012"], ["Item B", "34"], ["", ""]]
    if blank_middle:
        data = [data[0], data[3], data[1], data[2]]
    for r, row in enumerate(data):
        for c, text in enumerate(row):
            if text:
                canvas.drawString(xs[c] + 4, 240 - ys[r] - 18, text)
    canvas.save()
    stream.seek(0)
    if shifted:
        writer = PdfWriter()
        writer.append_pages_from_reader(PdfReader(stream))
        writer.pages[0].mediabox = RectangleObject([420, 80, 820, 240])
        changed = io.BytesIO()
        writer.write(changed)
        changed.seek(0)
        stream = changed
    document = pdfplumber.open(stream)
    page = document.pages[0]
    table = ruled_tables(page)[0]
    return document, page, table


class TrailingBlankTests(unittest.TestCase):
    def test_visible_ruled_blank_row_is_preserved_in_workbook(self):
        document, page, table = fixture()
        with document:
            before = copy.deepcopy(table)
            self.assertEqual(len(table["heights"]), 3)
            got = recover(table, page, table_from_pdf)
            self.assertEqual(table, before)
            self.assertEqual(len(got["heights"]), 4)
            self.assertEqual(got["heights"][-1], 80)
            self.assertEqual(sum(got["heights"]), got["bbox"][3] - got["bbox"][1])
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / "result.xlsx"
                write_workbook([dict(got, page=1, index=1)], target, "tables")
                book = load_workbook(target)
                sheet = book.active
                self.assertEqual(sheet.max_row, 4)
                self.assertEqual(sheet["B2"].value, "012")
                self.assertEqual(sheet["B3"].value, "34")
                self.assertEqual([sheet.cell(4, c).value for c in [1, 2]], [None, None])
                book.close()

    def test_shifted_media_origin_and_clipped_closed_rectangle(self):
        document, page, table = fixture(shifted=True, closed_rectangle=True)
        with document:
            got = recover(table, page, table_from_pdf)
            self.assertEqual(len(got["heights"]), 4)
            self.assertEqual(got["bbox"], table["bbox"])
            self.assertLessEqual(got["bbox"][3], page.bbox[3])

    def test_uncapped_independent_lines_do_not_invent_an_extra_grid_row(self):
        document, page, table = fixture(shifted=True)
        with document:
            self.assertIs(recover(table, page, table_from_pdf), table)

    def test_interior_empty_row_does_not_shift_verified_records(self):
        document, page, table = fixture(blank_middle=True)
        with document:
            self.assertIs(recover(table, page, table_from_pdf), table)

    def test_changed_value_or_span_cannot_be_replaced_by_physical_grid(self):
        for field, value in [("text", "120"), ("cs", 2)]:
            document, page, table = fixture()
            with document:
                table["cells"][3][field] = value
                self.assertIs(recover(table, page, table_from_pdf), table)

    def test_existing_complete_height_and_unrelated_bounds_are_unchanged(self):
        for field in ["height", "bounds", "nonfinite"]:
            document, page, table = fixture()
            with document:
                if field == "height":
                    table["bbox"][3] = table["bbox"][1] + sum(table["heights"])
                elif field == "bounds":
                    table["bbox"][1] += 5
                else:
                    table["heights"][0] = float("nan")
                self.assertIs(recover(table, page, table_from_pdf), table)
