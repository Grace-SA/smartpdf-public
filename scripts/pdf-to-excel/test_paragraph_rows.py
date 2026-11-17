import copy
import sys
import tempfile
import unittest
from pathlib import Path

import pdfplumber
from reportlab.pdfgen import canvas
from pdfplumber.utils import extract_text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_paragraph_rows import recover
from layout_tables import local_box


class ParagraphRowsTests(unittest.TestCase):
    def fixture(self, root, mode="normal"):
        path = root / (mode + ".pdf")
        pdf = canvas.Canvas(str(path), pagesize=(610, 400))
        pdf.setFont("Helvetica", 9)
        xs = [35, 165, 365]
        ys = [350, 325, 300, 240, 210, 185, 125]
        values = [
            ["Source", "Definition", "Examples"],
            ["Fixed", "", ""],
            [
                "Primary",
                "Factory emissions over\nannual reporting periods.",
                "Steel makers and\nchemical facilities.",
            ],
            [
                "Secondary",
                "Smaller facilities across\nurban service areas.",
                "Dry cleaners and auto\nrepair facilities in towns.",
            ],
            ["Mobile", "", ""],
            [
                "Road",
                "Moving sources on public\ntransport routes.",
                "Cars buses trucks and\nother service vehicles.",
            ],
            [
                "Nonroad",
                "Portable equipment with\nother engine sources.",
                "Construction machinery and\nwatercraft and garden tools.",
            ],
        ]
        for x in [30, 160, 360, 580]:
            if mode == "rule" and x == 360:
                continue
            pdf.line(x, 80, x, 365)
        for y in [365, 80]:
            pdf.line(30, y, 580, y)
        for row, line in enumerate(values):
            for col, text in enumerate(line):
                for n, part in enumerate(text.split("\n")):
                    y = (
                        ys[row]
                        - n * 11
                        - (8 if mode == "alignment" and col == 0 and row == 2 else 0)
                    )
                    pdf.drawString(xs[col], y, part)
        if mode == "extra":
            pdf.drawString(500, 90, "unmodeled")
        pdf.save()
        return path, values, xs, ys

    def prediction(self, page, values, xs, ys):
        cells = []
        for row, line in enumerate(values):
            for col, text in enumerate(line):
                if not text:
                    continue
                l = [30, 160, 360][col]
                r = [160, 360, 580][col]
                top = 400 - ys[row] - 10
                bottom = 400 - ys[row] + len(text.split("\n")) * 11
                chars = [
                    c
                    for c in page.chars
                    if l <= (c["x0"] + c["x1"]) / 2 < r
                    and top <= (c["top"] + c["bottom"]) / 2 < bottom
                ]
                box = [
                    min(c["x0"] for c in chars),
                    min(c["top"] for c in chars),
                    max(c["x1"] for c in chars),
                    max(c["bottom"] for c in chars),
                ]
                cells.append(
                    dict(
                        text=extract_text(chars, x_tolerance=2, y_tolerance=2),
                        bbox=local_box(box, page),
                        start_row_offset_idx=row,
                        end_row_offset_idx=row + 1,
                        start_col_offset_idx=col,
                        end_col_offset_idx=col + 1,
                        row_span=1,
                        col_span=1,
                        column_header=row == 0,
                    )
                )
        upper = next(
            c
            for c in cells
            if c["start_row_offset_idx"] == 2 and c["start_col_offset_idx"] == 2
        )
        lower = next(
            c
            for c in cells
            if c["start_row_offset_idx"] == 3 and c["start_col_offset_idx"] == 2
        )
        first, rest = lower["text"].split("\n", 1)
        upper["text"] += " " + first
        lower["text"] = rest
        upper["bbox"]["b"] = lower["bbox"]["t"] + 9
        lower["bbox"]["t"] += 11
        return dict(
            prov=[dict(page_no=1, bbox=local_box([30, 35, 580, 320], page))],
            data=dict(num_rows=7, num_cols=3, table_cells=cells),
        )

    def test_stub_aligned_paragraphs_recover_cross_row_text_without_changing_values(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            path, expected, xs, ys = self.fixture(Path(tmp))
            with pdfplumber.open(path) as doc:
                page = doc.pages[0]
                item = self.prediction(page, expected, xs, ys)
                before = copy.deepcopy(item)
                out = recover(item, page)
                self.assertEqual(item, before)
                actual = {
                    (c["start_row_offset_idx"], c["start_col_offset_idx"]): " ".join(
                        c["text"].split()
                    )
                    for c in out["data"]["table_cells"]
                }
                self.assertEqual(
                    actual,
                    {
                        (r, c): " ".join(text.split())
                        for r, row in enumerate(expected)
                        for c, text in enumerate(row)
                        if text
                    },
                )

    def test_unmodeled_text_missing_rule_misalignment_and_merged_cells_abstain(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ["extra", "rule", "alignment", "merged", "changed"]:
                with self.subTest(mode=mode):
                    path, values, xs, ys = self.fixture(Path(tmp), mode)
                    with pdfplumber.open(path) as doc:
                        page = doc.pages[0]
                        item = self.prediction(page, values, xs, ys)
                        if mode == "merged":
                            item["data"]["table_cells"][0]["row_span"] = 2
                        if mode == "changed":
                            item["data"]["table_cells"][0]["text"] = "Different"
                        self.assertEqual(recover(item, page), item)
