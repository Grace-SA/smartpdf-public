import copy
from types import SimpleNamespace
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_tables import adapt_table, prefer_native, LayoutError
from text_tables import conservative_aligned_tables


class LayoutTests(unittest.TestCase):
    def test_currency_recovery_requires_complete_grid_and_identical_number(self):
        from layout_tables import restore_rotated_headers

        model = dict(
            widths=[40, 40],
            heights=[20, 20],
            cells=[
                dict(r=0, c=0, rs=1, cs=1, text="Item"),
                dict(r=0, c=1, rs=1, cs=1, text="Amount"),
                dict(r=1, c=0, rs=1, cs=1, text="00123"),
                dict(r=1, c=1, rs=1, cs=1, text="001.20"),
            ],
        )
        native = copy.deepcopy(model)
        native["closedGrid"] = True
        native["cells"][-1]["text"] = "$ 001.20"
        self.assertEqual(
            restore_rotated_headers(model, [native])["cells"][-1]["text"], "$ 001.20"
        )
        self.assertEqual(model["cells"][-1]["text"], "001.20")
        for value in ["$ 001.21", "$ 1.20", "$ 001.2", "$ -001.20", "€$ 001.20"]:
            native["cells"][-1]["text"] = value
            self.assertIs(restore_rotated_headers(model, [native]), model)
        native["cells"][-1]["text"] = "$ 001.20"
        self.assertIs(
            restore_rotated_headers(model, [native, copy.deepcopy(native)]), model
        )
        native["closedGrid"] = False
        self.assertIs(restore_rotated_headers(model, [native]), model)

    def test_clipped_word_glyphs_require_unique_complete_visible_source_word(self):
        import tempfile
        import pdfplumber
        from reportlab.pdfgen import canvas
        from layout_tables import source_cell_text, local_box

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "words.pdf"
            pdf = canvas.Canvas(str(path), pagesize=(300, 300))
            pdf.setFont("Helvetica", 12)
            pdf.drawString(40, 240, "2005–06")
            pdf.drawString(40, 210, "2005–06")
            pdf.save()
            with pdfplumber.open(path) as doc:
                page = doc.pages[0]
                first = page.extract_words()[0]
                b = [first["x0"] + 6, first["top"], first["x1"] - 6, first["bottom"]]
                box = local_box(b, page)
                self.assertEqual(source_cell_text("2005-06", box, page), "2005–06")
                self.assertEqual(source_cell_text("2005-07", box, page), "2005-07")
                both = local_box([b[0], b[1], b[2], b[3] + 31], page)
                self.assertEqual(source_cell_text("2005-06", both, page), "2005-06")
                # Full source word crosses the visible crop. Do not bring its
                # hidden first glyph back into the workbook.
                page.cropbox = (first["x0"] + 3, 0, 300, 300)
                del page._excel_source_words
                self.assertEqual(
                    source_cell_text("2005-06", local_box(b, page), page), "2005-06"
                )

    def test_rotated_header_recovery_requires_unique_unchanged_data(self):
        from layout_tables import restore_rotated_headers

        model = dict(
            widths=[40, 40],
            heights=[20, 20],
            cells=[
                dict(r=0, c=0, rs=1, cs=1, text="workers"),
                dict(r=0, c=1, rs=1, cs=1, text="Count"),
                dict(r=1, c=0, rs=1, cs=1, text="Region A"),
                dict(r=1, c=1, rs=1, cs=1, text="00123"),
            ],
        )
        native = copy.deepcopy(model)
        native["cells"][0]["text"] = "Movement of\nworkers"
        restored = restore_rotated_headers(model, [native])
        self.assertEqual(restored["cells"][0]["text"], "Movement of\nworkers")
        self.assertEqual(restored["cells"][3]["text"], "00123")
        self.assertEqual(model["cells"][0]["text"], "workers")
        self.assertIs(
            restore_rotated_headers(model, [native, copy.deepcopy(native)]), model
        )
        native["cells"][3]["text"] = "123"
        self.assertIs(restore_rotated_headers(model, [native]), model)
        native["cells"][3]["text"] = "00123"
        native["cells"][0]["text"] = "2026 workers"
        self.assertIs(restore_rotated_headers(model, [native]), model)

    def test_headerless_numeric_tables_preserve_independent_row_counts(self):
        words = []
        expected = []
        for left, rows in [(20, 8), (240, 6)]:
            values = []
            for r in range(rows):
                for c in range(3):
                    text = f"{r * 3 + c:03}"
                    values.append(text)
                    words.append(
                        dict(
                            x0=left + c * 40,
                            x1=left + c * 40 + 18,
                            top=r * 20,
                            bottom=r * 20 + 10,
                            text=text,
                        )
                    )
            expected.append(values)
        page = SimpleNamespace(extract_words=lambda **_: words)
        found = conservative_aligned_tables(page)
        self.assertEqual([len(t["heights"]) for t in found], [8, 6])
        self.assertEqual([[c["text"] for c in t["cells"]] for t in found], expected)
        # Numeric chart labels, a dropped value, and prose on the page cannot
        # satisfy the complete numeric-page fallback.
        page.curves = [{"object_type": "curve"}]
        self.assertEqual(conservative_aligned_tables(page), [])
        page.curves = []
        saved = words.pop(7)
        self.assertEqual(conservative_aligned_tables(page), [])
        words.append(saved)
        words.append(dict(x0=20, x1=100, top=200, bottom=210, text="paragraph"))
        self.assertEqual(conservative_aligned_tables(page), [])

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

    def test_physical_span_recovers_label_without_joining_numeric_rows(self):
        from layout_tables import restore_native_spans

        model = dict(
            cells=[
                dict(r=0, c=0, rs=1, cs=1, text="Chronic fatigue"),
                dict(r=1, c=0, rs=1, cs=1, text="syndrome"),
                dict(r=0, c=1, rs=1, cs=1, text="00123"),
                dict(r=1, c=1, rs=1, cs=1, text="00456"),
            ]
        )
        physical = dict(
            closedGrid=True,
            cells=[
                dict(r=0, c=0, rs=2, cs=1, text="Chronic fatigue\nsyndrome"),
                dict(r=0, c=1, rs=2, cs=1, text="00123\n00456"),
            ],
        )
        result = restore_native_spans(model, physical)
        self.assertIn(physical["cells"][0], result["cells"])
        self.assertNotIn(physical["cells"][1], result["cells"])
        self.assertEqual(
            [c["text"] for c in result["cells"] if c["c"] == 1], ["00123", "00456"]
        )
        self.assertEqual(len(model["cells"]), 4)
        physical["closedGrid"] = False
        self.assertIs(restore_native_spans(model, physical), model)

    def test_physical_span_does_not_combine_names_or_expand_existing_merge(self):
        from layout_tables import restore_native_spans

        model = dict(
            cells=[
                dict(r=0, c=0, rs=1, cs=1, text="Alpha"),
                dict(r=1, c=0, rs=1, cs=1, text="Beta"),
            ]
        )
        physical = dict(
            closedGrid=True, cells=[dict(r=0, c=0, rs=2, cs=1, text="Alpha Beta")]
        )
        self.assertIs(restore_native_spans(model, physical), model)
        model = dict(
            cells=[
                dict(r=0, c=0, rs=2, cs=1, text="Heading"),
                dict(r=2, c=0, rs=1, cs=1, text=""),
            ]
        )
        physical["cells"] = [dict(r=0, c=0, rs=3, cs=1, text="Heading")]
        self.assertIs(restore_native_spans(model, physical), model)

    def test_pdf_glyphs_restore_punctuation_without_guessing_numbers(self):
        from layout_tables import source_cell_text

        def page_for(text):
            chars = [
                dict(
                    text=c,
                    x0=i * 6,
                    x1=i * 6 + 6,
                    top=10,
                    bottom=20,
                    doctop=10,
                    upright=True,
                    height=10,
                    width=6,
                )
                for i, c in enumerate(text)
            ]
            return SimpleNamespace(height=800, chars=chars)

        box = dict(l=0, t=8, r=150, b=22, coord_origin="TOPLEFT")
        self.assertEqual(
            source_cell_text("10-20 'a'", box, page_for("10–20 ‘A’")), "10–20 ‘A’"
        )
        self.assertEqual(source_cell_text("00123", box, page_for("00124")), "00123")
        self.assertEqual(source_cell_text("10-20", box, page_for("10–20 30")), "10-20")

    def test_pdf_soft_wrap_does_not_double_excel_line_breaks(self):
        from layout_tables import source_cell_text

        chars = []
        for row, value in enumerate(("Alpha", "– Beta")):
            for i, char in enumerate(value):
                chars.append(
                    dict(
                        text=char,
                        x0=i * 6,
                        x1=i * 6 + 6,
                        top=10 + row * 20,
                        bottom=20 + row * 20,
                        doctop=10 + row * 20,
                        upright=True,
                        height=10,
                        width=6,
                    )
                )
        page = SimpleNamespace(height=800, chars=chars)
        box = dict(l=0, t=8, r=150, b=45, coord_origin="TOPLEFT")
        self.assertEqual(source_cell_text("Alpha - Beta", box, page), "Alpha – Beta")

    def test_source_glyph_recovery_ignores_only_complete_neighbour_lines(self):
        from layout_tables import source_cell_text

        def page_for(lines):
            chars = []
            for row, line in enumerate(lines):
                for i, char in enumerate(line):
                    chars.append(
                        dict(
                            text=char,
                            x0=i * 6,
                            x1=i * 6 + 6,
                            top=10 + row * 20,
                            bottom=20 + row * 20,
                            doctop=10 + row * 20,
                            upright=True,
                            height=10,
                            width=6,
                        )
                    )
            return SimpleNamespace(height=800, chars=chars)

        box = dict(l=0, t=8, r=300, b=85, coord_origin="TOPLEFT")
        self.assertEqual(source_cell_text("-", box, page_for(["Header", "–"])), "–")
        self.assertEqual(
            source_cell_text("10-20", box, page_for(["Header", "10–20 30"])), "10-20"
        )
        self.assertEqual(
            source_cell_text("10-20", box, page_for(["10–20", "10–20"])), "10-20"
        )
        self.assertEqual(
            source_cell_text("00123", box, page_for(["Header", "00124"])), "00123"
        )

    def test_stacked_numeric_values_are_not_a_recovered_grid(self):
        from layout_tables import independent_grid

        table = dict(
            closedGrid=True,
            widths=[50, 50],
            heights=[20, 20],
            cells=[
                dict(r=0, c=0, text="Code"),
                dict(r=0, c=1, text="Amount"),
                dict(r=1, c=0, text="A"),
                dict(r=1, c=1, text="100\n200"),
            ],
        )
        self.assertFalse(independent_grid(table))
        table["cells"][-1]["text"] = "00123"
        self.assertTrue(independent_grid(table))

    @staticmethod
    def prediction_cell(row, col, text, *, span=1, header=False, top=None):
        top = row * 15 if top is None else top
        return dict(
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=col,
            end_col_offset_idx=col + span,
            row_span=1,
            col_span=span,
            text=text,
            column_header=header,
            bbox=dict(
                l=col * 80,
                t=top,
                r=(col + span) * 80,
                b=top + 8,
                coord_origin="TOPLEFT",
            ),
        )

    def test_repeated_header_splits_tables_without_losing_values(self):
        from layout_tables import refine_predictions

        c = self.prediction_cell
        item = dict(
            prov=[dict(bbox=dict(l=0, t=0, r=240, b=200, coord_origin="TOPLEFT"))],
            data=dict(num_rows=10, num_cols=3, table_cells=[]),
        )
        for start in (0, 5):
            item["data"]["table_cells"].append(
                c(start, 1, "Measures", span=2, header=True)
            )
            for col, text in enumerate(("Code", "2024", "2025")):
                item["data"]["table_cells"].append(c(start + 1, col, text, header=True))
            for r in range(start + 2, start + 5):
                for col, text in enumerate(
                    (f"ID-{r}", "00123", "99999999999999999999")
                ):
                    item["data"]["table_cells"].append(c(r, col, text))
        parts = refine_predictions(item, SimpleNamespace(height=800, edges=[]))
        self.assertEqual(len(parts), 2)
        self.assertEqual([p["data"]["num_rows"] for p in parts], [5, 5])
        for p in parts:
            table = adapt_table(p, self.page)
            code = next(c for c in table["cells"] if c["text"] == "Code")
            self.assertEqual((code["r"], code["rs"]), (0, 2))
            self.assertEqual(sum(c["text"] == "00123" for c in table["cells"]), 3)
        self.assertEqual(item["data"]["num_rows"], 10)  # input is not mutated

    def test_header_merge_respects_a_visible_separator(self):
        from layout_tables import restore_stub_header

        c = self.prediction_cell
        data = dict(
            table_cells=[
                c(0, 1, "Group", span=2, header=True),
                c(1, 0, "Code", header=True),
                c(1, 1, "A", header=True),
                c(1, 2, "B", header=True),
            ]
        )
        original = copy.deepcopy(data)
        restore_stub_header(
            data,
            SimpleNamespace(
                height=800, edges=[dict(orientation="h", top=12, x0=0, x1=80)]
            ),
        )
        self.assertEqual(data, original)

    def test_physical_recovery_requires_complete_grid_and_unchanged_digits(self):
        from layout_tables import recover_ruled_prediction

        item = copy.deepcopy(self.item)
        model = adapt_table(item, self.page)
        model["closedGrid"] = True
        recovered = recover_ruled_prediction(item, self.page, [model])
        self.assertEqual(recovered["method"], "ruled-recovery")
        altered = copy.deepcopy(model)
        altered["cells"][1]["text"] = "00124"
        self.assertIsNone(recover_ruled_prediction(item, self.page, [altered]))
        model["closedGrid"] = False
        self.assertIsNone(recover_ruled_prediction(item, self.page, [model]))

    def test_native_heading_extension_cannot_change_an_identifier(self):
        model = adapt_table(self.item, self.page)
        native = copy.deepcopy(model)
        native["cells"][0]["text"] = "Complete Heading"
        self.assertIs(prefer_native(model, [native]), native)
        native["cells"][1]["text"] = "001230"
        self.assertIs(prefer_native(model, [native]), model)

    def test_dot_leaders_do_not_create_a_column_but_real_values_do(self):
        from layout_tables import refine_predictions

        c = self.prediction_cell
        entries = [
            c(0, 0, "Label", span=2, header=True),
            c(0, 2, "Amount", header=True),
        ]
        for row in range(1, 5):
            entries += [
                c(row, 0, f"Key{row}"),
                c(row, 1, "............"),
                c(row, 2, "00123"),
            ]
        item = dict(
            prov=[dict(bbox=dict(l=0, t=0, r=240, b=80, coord_origin="TOPLEFT"))],
            data=dict(num_rows=5, num_cols=3, table_cells=entries),
        )
        result = refine_predictions(item, self.page)[0]
        self.assertEqual(result["data"]["num_cols"], 2)
        table = adapt_table(result, self.page)
        self.assertEqual(sum(c["text"] == "00123" for c in table["cells"]), 4)
        entries[-2]["text"] = "Pending..."
        self.assertEqual(refine_predictions(item, self.page)[0]["data"]["num_cols"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
