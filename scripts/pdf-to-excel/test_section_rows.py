import copy
import sys
import tempfile
import unittest
from pathlib import Path

import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_section_rows import recover


class SectionRowTests(unittest.TestCase):
    def fixture(
        self,
        path,
        closed=False,
        incomplete=False,
        crop_word=False,
        symbols=False,
        wide=False,
        wrapped=False,
        soft_outdent=False,
    ):
        p = canvas.Canvas(str(path), pagesize=(450, 650))
        cells = []
        expected = []
        y = 55
        index = 0

        def line(values, bold=False, continuation=False, close_label=False):
            nonlocal y, index
            font = "Helvetica-Bold" if bold else "Helvetica"
            p.setFont(font, 10)
            for col, text in enumerate(values):
                if not text:
                    continue
                x = (
                    (
                        42
                        if close_label
                        else 40 if bold or text.startswith("Group") else 50
                    )
                    if col == 0
                    else 130 + col * 50
                )
                p.drawString(x, 650 - y, text)
                cells.append(
                    dict(
                        start_row_offset_idx=index,
                        end_row_offset_idx=index + 1,
                        start_col_offset_idx=col,
                        end_col_offset_idx=col + 1,
                        row_span=1,
                        col_span=1,
                        text=text,
                        column_header=index == 0,
                        row_header=col == 0,
                        row_section=False,
                        bbox=dict(
                            l=x,
                            t=y - 10,
                            r=x + stringWidth(text, font, 10),
                            b=y + 2,
                            coord_origin="TOPLEFT",
                        ),
                    )
                )
            expected.append(values)
            index += 1
            y += 13

        line(["Label", "Count", "Rate", "Size", "Total"], True)
        p.line(30, 590, 420, 590)
        y = 75
        for group, count in [("Group A", 10), ("Group B", 10), ("Group C", 5)]:
            if soft_outdent and group == "Group C":
                y += 10
            label = (
                group + " extended category label"
                if wide and group == "Group C"
                else group
            )
            line(
                [label, "", "", "", ""],
                group != "Group B" and not (soft_outdent and group == "Group C"),
            )
            if wrapped and group == "Group C":
                p.setFont("Helvetica-Bold", 10)
                p.drawString(48, 650 - y, "continued category")
                cells[-1]["text"] += " continued category"
                cells[-1]["bbox"]["b"] = y + 2
                cells[-1]["bbox"]["r"] = max(
                    cells[-1]["bbox"]["r"],
                    48 + stringWidth("continued category", "Helvetica-Bold", 10),
                )
                expected[-1][0] += "\ncontinued category"
                y += 13
            for j in range(count):
                values = [f"Item {j}", str(100 + j), str(j + 1), f"({j+2}.1)", "Ref."]
                if incomplete and group == "Group B" and j == 4:
                    values[2] = ""
                if symbols:
                    values[1] = "$" + values[1]
                    values[4] = ["†", "‡", "na"][j % 3]
                line(values, close_label=soft_outdent and group == "Group B" and j == 9)
                if group == "Group A" and j == 3:
                    y -= 4
                    p.setFont("Helvetica", 10)
                    p.drawString(52, 650 - y, "continued")
                    # Model correctly knows this phrase belongs to the same
                    # cell but also compresses an independent later section.
                    stub = next(
                        c for c in reversed(cells) if c["start_col_offset_idx"] == 0
                    )
                    stub["text"] += " continued"
                    stub["bbox"]["b"] = y + 2
                    expected[-1][0] += "\ncontinued"
                    y += 13
        bottom = y - 8
        p.line(30, 650 - bottom, 420, 650 - bottom)
        if closed:
            p.line(30, 590, 30, 650 - bottom)
            p.line(420, 590, 420, 650 - bottom)
        p.save()
        target = next(c for c in cells if c["text"] == "Group B")
        cut = target["start_row_offset_idx"]
        previous = next(
            c
            for c in cells
            if c["start_row_offset_idx"] == cut - 1 and c["start_col_offset_idx"] == 0
        )
        previous["text"] += " Group B"
        previous["bbox"]["b"] = target["bbox"]["b"]
        cells.remove(target)
        for c in cells:
            if c["start_row_offset_idx"] >= cut:
                c["start_row_offset_idx"] -= 1
                c["end_row_offset_idx"] -= 1
        item = dict(
            prov=[
                dict(
                    page_no=1,
                    bbox=dict(l=30, t=40, r=420, b=bottom, coord_origin="TOPLEFT"),
                )
            ],
            data=dict(num_rows=index - 1, num_cols=5, table_cells=cells),
        )
        if crop_word:
            item["prov"][0]["bbox"]["l"] = 55
        return item, expected

    def test_preserves_wrapped_label_and_restores_compressed_outdented_section(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sections.pdf"
            item, expected = self.fixture(path)
            before = copy.deepcopy(item)
            with pdfplumber.open(path) as pdf:
                result = recover(item, pdf.pages[0])
            self.assertIsNot(result, item)
            self.assertEqual(item, before)
            self.assertEqual(result["data"]["num_rows"], len(expected))
            actual = [[""] * 5 for _ in expected]
            for c in result["data"]["table_cells"]:
                actual[c["start_row_offset_idx"]][c["start_col_offset_idx"]] = c["text"]
                self.assertEqual((c["row_span"], c["col_span"]), (1, 1))
            self.assertEqual(actual, expected)

    def test_closed_multiline_grid_incomplete_data_and_cut_words_abstain(self):
        with tempfile.TemporaryDirectory() as temp:
            for option in ["closed", "incomplete", "crop_word"]:
                path = Path(temp) / (option + ".pdf")
                item, _ = self.fixture(path, **{option: True})
                with pdfplumber.open(path) as pdf:
                    self.assertIs(recover(item, pdf.pages[0]), item, option)

    def test_currency_footnote_symbols_and_literal_na_preserve_values(self):
        self.assert_recovery(symbols=True)

    def test_wide_section_caption_does_not_move_words_into_numeric_columns(self):
        self.assert_recovery(wide=True)

    def test_indented_section_continuation_stays_with_source_backed_caption(self):
        self.assert_recovery(wrapped=True)

    def test_section_gap_and_following_indent_allow_small_preceding_outdent(self):
        self.assert_recovery(soft_outdent=True)

    def assert_recovery(self, **options):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sections.pdf"
            item, expected = self.fixture(path, **options)
            original = copy.deepcopy(item)
            with pdfplumber.open(path) as pdf:
                result = recover(item, pdf.pages[0])
            self.assertIsNot(result, item)
            self.assertEqual(item, original)
            actual = [[""] * 5 for _ in range(result["data"]["num_rows"])]
            for c in result["data"]["table_cells"]:
                actual[c["start_row_offset_idx"]][c["start_col_offset_idx"]] = c["text"]
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
