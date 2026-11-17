"""Source-backed row recovery: preserve numbers and reject ambiguous layouts."""

import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_rows import repair_merged_rows
from layout_tables import adapt_table


def fixture():
    chars, cells = [], []
    values = [["Name", "Code", "Amount", "Count"]] + [
        [chr(64 + r), f"{100 + r:05}", f"{r}.50", str(9000 + r)] for r in range(1, 8)
    ]
    for row, entries in enumerate(values):
        for col, value in enumerate(entries):
            for i, char in enumerate(value):
                chars.append(
                    dict(
                        text=char,
                        x0=10 + col * 100 + i * 4,
                        x1=14 + col * 100 + i * 4,
                        top=10 + row * 20,
                        bottom=18 + row * 20,
                        doctop=10 + row * 20,
                        upright=True,
                        width=4,
                        height=8,
                    )
                )
    for model_row, source_rows in enumerate(([0], [1], [2, 3], [4], [5], [6], [7])):
        for col in range(4):
            cells.append(
                dict(
                    start_row_offset_idx=model_row,
                    end_row_offset_idx=model_row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    row_span=1,
                    col_span=1,
                    column_header=model_row == 0,
                    text=" ".join(values[r][col] for r in source_rows),
                    bbox=dict(
                        l=10 + col * 100,
                        r=60 + col * 100,
                        t=10 + min(source_rows) * 20,
                        b=18 + max(source_rows) * 20,
                        coord_origin="TOPLEFT",
                    ),
                )
            )
    item = dict(
        data=dict(num_rows=7, num_cols=4, table_cells=cells),
        prov=[dict(bbox=dict(l=0, t=0, r=400, b=170, coord_origin="TOPLEFT"))],
    )
    return item, SimpleNamespace(height=200, width=400, chars=chars, edges=[]), values


class RowRecoveryTests(unittest.TestCase):
    def test_separates_rows_and_preserves_all_literal_values(self):
        item, page, values = fixture()
        before = copy.deepcopy(item)
        result = repair_merged_rows(item, page)
        self.assertEqual(item, before)
        self.assertEqual(result["data"]["num_rows"], 8)
        table = adapt_table(result, page)
        actual = {(c["r"], c["c"]): c["text"] for c in table["cells"]}
        self.assertEqual(
            actual,
            {(r, c): v for r, row in enumerate(values) for c, v in enumerate(row)},
        )

    def test_recovers_missing_numeric_line_only_with_two_other_columns(self):
        item, page, values = fixture()
        cell = next(
            c
            for c in item["data"]["table_cells"]
            if c["start_row_offset_idx"] == 2 and c["start_col_offset_idx"] == 3
        )
        cell["text"] = values[3][3]
        result = repair_merged_rows(item, page)
        self.assertEqual(result["data"]["num_rows"], 8)
        actual = {
            (c["start_row_offset_idx"], c["start_col_offset_idx"]): c["text"]
            for c in result["data"]["table_cells"]
        }
        self.assertEqual(actual[2, 3], values[2][3])
        self.assertEqual(actual[3, 3], values[3][3])

    def test_changed_digit_cannot_be_hidden_by_row_recovery(self):
        item, page, _ = fixture()
        item["data"]["table_cells"][9]["text"] = "00102 99999"
        self.assertEqual(repair_merged_rows(item, page), item)

    def test_one_numeric_column_is_not_enough_evidence(self):
        item, page, values = fixture()
        for col in (2, 3):
            item["data"]["table_cells"][8 + col]["text"] = values[3][col]
        self.assertEqual(repair_merged_rows(item, page), item)

    def test_borders_preserve_intentional_multiline_cells(self):
        item, page, _ = fixture()
        page.edges = [dict(orientation="h", top=y, x0=0, x1=400) for y in (45, 85)] + [
            dict(orientation="v", top=45, bottom=85, x0=x, x1=x) for x in (0, 400)
        ]
        self.assertEqual(repair_merged_rows(item, page), item)
        page.edges.append(dict(orientation="h", top=65, x0=0, x1=400))
        self.assertEqual(repair_merged_rows(item, page)["data"]["num_rows"], 8)

    def test_misaligned_source_rows_are_not_split(self):
        item, page, _ = fixture()
        for char in page.chars:
            if 210 <= char["x0"] < 260 and 50 <= char["top"] <= 70:
                char["top"] += 6
                char["bottom"] += 6
                char["doctop"] += 6
        self.assertEqual(repair_merged_rows(item, page), item)

    def test_invalid_coordinates_are_left_to_the_model_validator(self):
        item, page, _ = fixture()
        item["data"]["table_cells"][9]["end_row_offset_idx"] = 99
        self.assertEqual(repair_merged_rows(item, page), item)


if __name__ == "__main__":
    unittest.main(verbosity=2)
