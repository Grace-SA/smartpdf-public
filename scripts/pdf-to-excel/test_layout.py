import copy
from types import SimpleNamespace
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_tables import adapt_table, prefer_native, LayoutError
from text_tables import conservative_aligned_tables


class LayoutTests(unittest.TestCase):
    def test_numeric_chart_axes_are_not_recovered_as_a_table(self):
        words = []
        for r, value in enumerate(["300", "250", "200", "150", "100", "50"]):
            for x in [20, 240]:
                words.append(
                    dict(x0=x, x1=x + 24, top=r * 30, bottom=r * 30 + 10, text=value)
                )
        page = SimpleNamespace(extract_words=lambda **_: words)
        self.assertEqual(conservative_aligned_tables(page), [])

    def setUp(self):
        self.page = SimpleNamespace(height=800)
        self.item = {
            "prov": [{"bbox": dict(l=0, t=0, r=400, b=200, coord_origin="TOPLEFT")}],
            "data": {
                "num_rows": 2,
                "num_cols": 2,
                "table_cells": [
                    dict(
                        start_row_offset_idx=0,
                        start_col_offset_idx=0,
                        row_span=1,
                        col_span=2,
                        text="Heading",
                    ),
                    dict(
                        start_row_offset_idx=1,
                        start_col_offset_idx=0,
                        row_span=1,
                        col_span=1,
                        text="00123",
                    ),
                    dict(
                        start_row_offset_idx=1,
                        start_col_offset_idx=1,
                        row_span=1,
                        col_span=1,
                        text="12345678901234567890",
                    ),
                ],
            },
        }

    def test_model_adapter_preserves_spans_and_literal_values(self):
        result = adapt_table(self.item, self.page)
        self.assertEqual(result["cells"][0]["cs"], 2)
        self.assertEqual(result["cells"][1]["text"], "00123")
        self.assertEqual(result["cells"][2]["text"], "12345678901234567890")

    def test_overlapping_prediction_is_refused(self):
        self.item["data"]["table_cells"].append(
            dict(self.item["data"]["table_cells"][0])
        )
        with self.assertRaisesRegex(LayoutError, "overlapping"):
            adapt_table(self.item, self.page)

    def test_invalid_span_is_refused(self):
        self.item["data"]["table_cells"][0]["col_span"] = 3
        with self.assertRaisesRegex(LayoutError, "inconsistent"):
            adapt_table(self.item, self.page)

    def test_dimensions_and_cell_budget_are_bounded(self):
        self.item["data"]["num_rows"] = 200000
        with self.assertRaisesRegex(LayoutError, "budget"):
            adapt_table(self.item, self.page)
        self.item["data"]["num_rows"] = 2
        self.item["prov"][0]["bbox"]["r"] = float("nan")
        with self.assertRaisesRegex(LayoutError, "dimensions"):
            adapt_table(self.item, self.page)

    def test_blank_model_output_is_not_success(self):
        for cell in self.item["data"]["table_cells"]:
            cell["text"] = ""
        with self.assertRaisesRegex(LayoutError, "no readable text"):
            adapt_table(self.item, self.page)

    def test_native_fallback_cannot_drop_or_invent_values(self):
        model = adapt_table(self.item, self.page)
        native = copy.deepcopy(model)
        self.assertIs(prefer_native(model, [native]), native)
        native["cells"][1]["text"] = "123"
        self.assertIs(prefer_native(model, [native]), model)

    def test_native_fallback_requires_same_dimensions_and_location(self):
        model = adapt_table(self.item, self.page)
        native = copy.deepcopy(model)
        native["widths"].append(50)
        self.assertIs(prefer_native(model, [native]), model)
        native = copy.deepcopy(model)
        native["bbox"] = [500, 0, 900, 200]
        self.assertIs(prefer_native(model, [native]), model)


if __name__ == "__main__":
    unittest.main(verbosity=2)
