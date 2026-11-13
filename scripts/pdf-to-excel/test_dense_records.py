import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest

import pdfplumber
from openpyxl import load_workbook
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import ruled_tables, write_workbook, apply_source_typography
from layout_dense import dense_grid


def fixture(serials=None, extra_table=False):
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(600, 800))
    canvas.setFont("Helvetica", 8)
    xs = [20, 60, 130, 270, 370, 460, 560]
    ys = [760 - 28 * r for r in range(26)]
    for x in xs:
        canvas.line(x, ys[-1], x, ys[0])
    for y in ys:
        canvas.line(xs[0], y, xs[-1], y)
    rows = [["Serial", "Name", "Description", "Code", "Amount", "Status"]] + [
        [str(r), f"Item {r}", "First part\nSecond part", f"{r:05}", "-1.20", "Active"]
        for r in range(1, 25)
    ]
    if serials:
        for r, value in serials.items():
            rows[r][0] = value
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            for line, value in enumerate(text.splitlines()):
                canvas.drawString(xs[c] + 3, ys[r] - 11 - line * 10, value)
    if extra_table:
        canvas.setFont("Helvetica", 5)
        for r in range(3):
            canvas.drawString(30, 795 - r * 9, f"Extra{r}")
            canvas.drawString(160, 795 - r * 9, str(r + 1))
    canvas.save()
    stream.seek(0)
    return pdfplumber.open(stream)


class DenseRecordsTests(unittest.TestCase):
    def test_wrapped_physical_records_keep_all_rows_columns_and_literal_values(self):
        with fixture() as doc:
            page = doc.pages[0]
            native = ruled_tables(page)
            before = copy.deepcopy(native)
            result = dense_grid(page, native)
            self.assertIsNotNone(result)
            self.assertEqual(native, before)
            self.assertEqual(result["cells"], native[0]["cells"])
            result["fontSize"] = 8
            apply_source_typography(result, page)
            result.update(page=1, index=1)
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / "records.xlsx"
                write_workbook([result], target, "tables")
                book = load_workbook(target)
                self.assertEqual((book.active.max_row, book.active.max_column), (25, 6))
                self.assertEqual(book.active["C25"].value, "First part\nSecond part")
                self.assertEqual(book.active["D25"].value, "00024")
                self.assertEqual(book.active["E25"].value, "-1.20")
                book.close()

    def test_missing_repeated_reordered_and_decorated_serials_keep_model_path(self):
        for serials in [{5: ""}, {5: "4"}, {5: "6", 6: "5"}, {5: "05"}, {5: "5."}]:
            with self.subTest(serials=serials), fixture(serials) as doc:
                self.assertIsNone(dense_grid(doc.pages[0], ruled_tables(doc.pages[0])))

    def test_numbered_grid_does_not_suppress_another_borderless_table(self):
        with fixture(extra_table=True) as doc:
            self.assertIsNone(dense_grid(doc.pages[0], ruled_tables(doc.pages[0])))

    def test_changed_punctuation_missing_glyph_and_merged_cell_are_rejected(self):
        with fixture() as doc:
            page = doc.pages[0]
            native = ruled_tables(page)
            for mutation in ["sign", "word", "span", "coverage"]:
                changed = copy.deepcopy(native)
                if mutation == "sign":
                    changed[0]["cells"][10]["text"] = "1.20"
                elif mutation == "word":
                    changed[0]["cells"][8]["text"] = "First part"
                elif mutation == "span":
                    changed[0]["cells"][8]["rs"] = 2
                else:
                    changed[0]["closedGrid"] = False
                with self.subTest(mutation=mutation):
                    self.assertIsNone(dense_grid(page, changed))
