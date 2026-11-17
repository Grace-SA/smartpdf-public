import copy
import sys
import tempfile
import unittest
from pathlib import Path

import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_columns import recover
from layout_tables import local_box, adapt_table


class ColumnTests(unittest.TestCase):
    def fixture(self, root, mode="normal"):
        path = root / (mode + ".pdf")
        pdf = canvas.Canvas(str(path), pagesize=(480, 300))
        pdf.setFont("Helvetica", 10)
        for x in [30, 130, 230, 330, 450] + ([380] if mode == "separator" else []):
            pdf.line(x, 80, x, 250 if mode != "gap" or x != 330 else 140)
        pdf.line(30, 250, 450, 250)
        pdf.line(30, 80, 450, 80)
        expected = []
        for row in range(11):
            values = (
                ["Area", "Estimate", "Actual", "Amount"]
                if row == 0
                else [f"Zone{row}", str(row * 2), str(row * 3), str(row * 5)]
            )
            expected.append(values)
            for x, value in zip([35, 135, 235, 335], values):
                pdf.drawString(x, 235 - row * 14, value)
        pdf.drawString(390, 235, "2026" if mode == "number" else "USD")
        if mode == "extra":
            pdf.drawString(390, 100, "hidden")
        if mode == "data":
            pdf.drawString(390, 221, "17")
        pdf.save()
        return path, expected

    def prediction(self, page, mode):
        cells = []
        for word in page.extract_words():
            if word["text"] == "hidden":
                continue
            row = round((word["top"] - page.extract_words()[0]["top"]) / 14)
            col = 4 if word["x0"] >= 380 else int((word["x0"] - 30) / 100)
            cells.append(
                dict(
                    text=word["text"],
                    bbox=local_box(
                        [word["x0"], word["top"], word["x1"], word["bottom"]], page
                    ),
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    row_span=1,
                    col_span=1,
                    column_header=row == 0,
                )
            )
        return dict(
            prov=[dict(page_no=1, bbox=local_box([30, 50, 450, 220], page))],
            data=dict(num_rows=11, num_cols=5, table_cells=cells),
        )

    def test_continuous_separators_join_split_unit_header_without_extra_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, expected = self.fixture(Path(tmp))
            with pdfplumber.open(path) as doc:
                page = doc.pages[0]
                item = self.prediction(page, "normal")
                before = copy.deepcopy(item)
                result = recover(item, page)
                self.assertEqual(item, before)
                self.assertEqual(result["data"]["num_cols"], 4)
                table = adapt_table(result, page)
                actual = {(c["r"], c["c"]): c["text"] for c in table["cells"]}
                expected[0][-1] = "Amount USD"
                self.assertEqual(
                    actual,
                    {
                        (r, c): text
                        for r, row in enumerate(expected)
                        for c, text in enumerate(row)
                    },
                )
                self.assertTrue(all(c["cs"] == c["rs"] == 1 for c in table["cells"]))

    def test_real_separator_incomplete_rule_numeric_header_and_unmodeled_glyphs_abstain(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ["separator", "gap", "number", "extra", "data"]:
                with self.subTest(mode=mode):
                    path, _ = self.fixture(Path(tmp), mode)
                    with pdfplumber.open(path) as doc:
                        item = self.prediction(doc.pages[0], mode)
                        self.assertEqual(recover(item, doc.pages[0]), item)
