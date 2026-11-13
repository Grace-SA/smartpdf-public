"""Original synthetic scan-column contradiction regressions."""

import copy
import sys
import unittest
from pathlib import Path

for parent in Path(__file__).resolve().parents:
    if (parent / "server/pdf-to-excel").is_dir():
        sys.path.insert(0, str(parent / "server/pdf-to-excel"))
        break
from layout_tables import LayoutError
from ocr_layout import reject_inverted_scan_columns


def cell(col, left, row=0, top=10, text="value", origin="TOPLEFT"):
    box = {"l": left, "r": left + 10, "t": top, "b": top + 10, "coord_origin": origin}
    if origin == "BOTTOMLEFT":
        box.update(t=100 - top, b=90 - top)
    return {
        "start_row_offset_idx": row,
        "start_col_offset_idx": col,
        "row_span": 1,
        "col_span": 1,
        "text": text,
        "bbox": box,
    }


def check(cells):
    reject_inverted_scan_columns({"data": {"table_cells": cells}}, 100)


class ScanGeometryTests(unittest.TestCase):
    def test_ordered_and_shuffled_input(self):
        check([cell(1, 30), cell(0, 10), cell(2, 50)])

    def test_reversed_and_cyclic_columns_refused(self):
        for cols in [
            [cell(0, 50), cell(1, 10)],
            [cell(0, 30), cell(1, 50), cell(5, 10)],
        ]:
            with self.assertRaisesRegex(LayoutError, "conflict"):
                check(cols)

    def test_mixed_origins(self):
        with self.assertRaisesRegex(LayoutError, "conflict"):
            check([cell(0, 50), cell(1, 10, origin="BOTTOMLEFT")])
        check([cell(0, 10, origin="BOTTOMLEFT"), cell(1, 50)])

    def test_separate_rows_and_text_lines_not_proof(self):
        check([cell(0, 50, row=0), cell(1, 10, row=1)])
        check([cell(0, 50, top=10), cell(1, 10, top=40)])

    def test_spans_and_missing_boxes_not_inferred(self):
        a = cell(0, 50)
        a["col_span"] = 2
        check([a, cell(2, 10)])
        a["col_span"] = 1
        a["row_span"] = 2
        check([a, cell(2, 10)])
        a = cell(0, 50)
        a.pop("bbox")
        check([a, cell(2, 10)])
        check([cell(0, 50, text=" "), cell(2, 10)])

    def test_touching_or_overlapping_boxes_not_proof(self):
        check([cell(0, 20), cell(1, 10)])
        check([cell(0, 19), cell(1, 10)])
        check([cell(0, 50, top=20), cell(1, 10, top=10)])

    def test_malformed_geometry_refused(self):
        for key, value in [
            ("l", float("nan")),
            ("t", float("inf")),
            ("r", True),
            ("l", "1"),
            ("r", -1),
            ("coord_origin", "unknown"),
        ]:
            c = cell(0, 10)
            c["bbox"][key] = value
            with self.assertRaises(LayoutError):
                check([c])

    def test_never_mutates_or_uses_cell_text_for_correction(self):
        c = [cell(0, 10, text="2004"), cell(1, 50, text="34.7")]
        before = copy.deepcopy(c)
        check(c)
        self.assertEqual(c, before)

    def test_large_ordered_row(self):
        check([cell(i, i * 20) for i in range(20000)])

    def test_integration_refuses_whole_result_without_fallback_or_overwrite(self):
        import os
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch

        import convert as engine
        from docling.datamodel.base_models import ConversionStatus
        from test_source_hidden_ocr import scanned_table

        def detected(inverted):
            cells = [cell(0, 50 if inverted else 10, row=r) for r in range(2)]
            cells += [cell(1, 10 if inverted else 50, row=r) for r in range(2)]
            raw = {
                "data": {"num_rows": 2, "num_cols": 2, "table_cells": cells},
                "prov": [
                    {
                        "bbox": {
                            "l": 0,
                            "t": 0,
                            "r": 100,
                            "b": 100,
                            "coord_origin": "TOPLEFT",
                        }
                    }
                ],
            }
            return SimpleNamespace(
                data=SimpleNamespace(num_rows=2, num_cols=2),
                model_dump=lambda: copy.deepcopy(raw),
            )

        fake = SimpleNamespace(
            convert=lambda *a, **k: SimpleNamespace(
                status=ConversionStatus.SUCCESS,
                document=SimpleNamespace(tables=[detected(False), detected(True)]),
            )
        )
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "scan.pdf"
            original = scanned_table(False, ruled=False)
            source.write_bytes(original)
            for existing in (False, True):
                target = Path(folder) / ("existing.xlsx" if existing else "new.xlsx")
                if existing:
                    target.write_bytes(b"prior output")
                with (
                    patch.dict(os.environ, {"PDF_EXCEL_MODELS": "mock-models"}),
                    patch.object(engine, "scan_tables", return_value=[]),
                    patch.object(engine, "_ocr", object()),
                    patch("ocr_layout.scan_converter", return_value=fake),
                    patch(
                        "text_tables.conservative_aligned_tables",
                        side_effect=AssertionError("must not fall back"),
                    ),
                    self.assertRaisesRegex(engine.ConversionError, "columns conflict"),
                ):
                    engine.convert(source, target, {"ocr": True})
                if existing:
                    self.assertEqual(target.read_bytes(), b"prior output")
                else:
                    self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
