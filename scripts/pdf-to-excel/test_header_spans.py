import copy
import io
import sys
import unittest
from pathlib import Path

import pdfplumber
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_header_spans import recover


class HeaderSpanTests(unittest.TestCase):
    def fixture(self, mode=""):
        buffer = io.BytesIO()
        canvas = Canvas(buffer, pagesize=(400, 240))
        canvas.setFont("Helvetica", 9)
        cells = []

        def cell(row, col, text, x, top, span=1, header=False):
            canvas.drawString(x, 240 - top - 9, text)
            width = stringWidth(text, "Helvetica", 9)
            cells.append(
                dict(
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + span,
                    row_span=1,
                    col_span=span,
                    text=text,
                    column_header=header,
                    bbox=dict(
                        l=x, t=top, r=x + width, b=top + 12, coord_origin="TOPLEFT"
                    ),
                )
            )

        cell(0, 0, "Day one", 64, 20, 3, True)
        cell(0, 4, "Day two", 184, 20, 2, True)
        cell(0, 6, "Day three", 264, 20, 2, True)
        for col in range(8):
            cell(
                1,
                col,
                "No." if col in [0, 3] else "Value",
                20 + col * 40,
                58 if mode != "baseline" or col != 3 else 65,
                header=True,
            )
        for row in range(2, 5):
            for col in range(8):
                cell(
                    row,
                    col,
                    str(100 + row * 10 + col),
                    20 + col * 40,
                    90 + (row - 2) * 20,
                )
        if mode != "no-rule":
            canvas.line(58 if mode != "wide-rule" else 15, 240 - 32, 138, 240 - 32)
        canvas.save()
        item = dict(
            data=dict(num_rows=5, num_cols=8, table_cells=cells),
            prov=[
                dict(
                    page_no=1,
                    bbox=dict(l=15, t=15, r=345, b=145, coord_origin="TOPLEFT"),
                )
            ],
        )
        return buffer, item

    def test_source_underline_excludes_repeated_stubs_without_changing_values(self):
        buffer, item = self.fixture()
        before = copy.deepcopy(item)
        with pdfplumber.open(buffer) as doc:
            result = recover(item, doc.pages[0])
            self.assertEqual(recover(result, doc.pages[0]), result)
        self.assertEqual(item, before)
        old = item["data"]["table_cells"]
        new = result["data"]["table_cells"]
        self.assertEqual([c["text"] for c in old], [c["text"] for c in new])
        self.assertEqual((new[0]["start_col_offset_idx"], new[0]["col_span"]), (1, 2))
        self.assertEqual(
            [
                (c["start_row_offset_idx"], c["row_span"])
                for c in new
                if c["text"] == "No."
            ],
            [(0, 2), (0, 2)],
        )
        self.assertEqual(new[11:], old[11:])

    def test_unproven_or_conflicting_header_geometry_abstains(self):
        for mode in [
            "no-rule",
            "wide-rule",
            "baseline",
            "source-text",
            "body-anchors",
            "child-span",
            "different-stub",
            "overlap",
        ]:
            with self.subTest(mode=mode):
                buffer, item = self.fixture(mode)
                cells = item["data"]["table_cells"]
                if mode == "source-text":
                    cells[0]["text"] = "Day changed"
                if mode == "body-anchors":
                    cells[-1]["text"] = ""
                if mode == "child-span":
                    cells[4]["col_span"] = 2
                if mode == "different-stub":
                    cells[3]["text"] = "Other"
                if mode == "overlap":
                    cells.append(copy.deepcopy(cells[3]))
                with pdfplumber.open(buffer) as doc:
                    self.assertIs(recover(item, doc.pages[0]), item)
