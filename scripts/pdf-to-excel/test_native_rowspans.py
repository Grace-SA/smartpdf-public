"""Original native ruled-cell fixtures; no public expected labels are used."""

import copy
import io
import sys
import unittest
from pathlib import Path

import pdfplumber
from pypdf import PdfWriter
from pypdf.annotations import FreeText
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_native_rowspans import recover


def fixture(mode="normal"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(450, 400))
    c.setFont("Helvetica", 10)
    cells = []

    def cell(row, col, text, x, top, rs=1, cs=1, draw=True):
        if draw and text:
            c.drawString(x, 400 - top - 8, text)
        cells.append(
            {
                "start_row_offset_idx": row,
                "end_row_offset_idx": row + rs,
                "start_col_offset_idx": col,
                "end_col_offset_idx": col + cs,
                "row_span": rs,
                "col_span": cs,
                "text": text,
                "column_header": row < 3,
                "bbox": {
                    "l": x,
                    "t": top,
                    "r": x + max(1, stringWidth(text, "Helvetica", 10)),
                    "b": top + 10,
                    "coord_origin": "TOPLEFT",
                },
            }
        )

    cell(0, 0, "Category", 30, 70, rs=3)
    cell(0, 1, "Metrics", 200, 25, cs=4)
    cell(1, 1, "Prior", 150, 45, cs=2)
    cell(1, 3, "Current", 280, 45)
    cell(1, 4, "Extra" if mode == "upper-nonempty" else "", 350, 45)
    for col in [1, 2, 3]:
        cell(2, col, f"Value{col}", 25 + col * 80, 70)
    cell(
        2,
        4,
        "Delta" if mode != "multiline" else "Delta\nOther",
        350,
        45 if mode == "wrong-row" else 70,
        draw=mode != "annotation",
    )
    for row in range(3, 7):
        for col in range(5):
            cell(row, col, f"{row}{col}", 30 + col * 80, 95 + (row - 3) * 20)
    for top in [20, 90, 110, 130, 150, 170]:
        c.line(20, 400 - top, 420, 400 - top)
    c.line(100, 360, 420, 360)
    c.line(100, 340, 420 if mode == "crossing" else 340, 340)
    for x in [20, 100, 420]:
        c.line(x, 380, x, 230)
    for x in [180, 260, 340]:
        c.line(x, 340 if x == 180 else 360, x, 230)
    if mode == "partial-crossing":
        c.line(350, 340, 360, 340)
    c.save()
    buf.seek(0)
    if mode == "annotation":
        writer = PdfWriter(clone_from=buf)
        writer.add_annotation(0, FreeText(text="Delta", rect=(350, 320, 380, 330)))
        new = io.BytesIO()
        writer.write(new)
        new.seek(0)
        buf = new
    doc = pdfplumber.open(buf)
    item = {
        "prov": [
            {"bbox": {"l": 20, "t": 20, "r": 420, "b": 170, "coord_origin": "TOPLEFT"}}
        ],
        "data": {"num_cols": 5, "num_rows": 7, "table_cells": cells},
    }
    return doc, doc.pages[0], item


class NativeRowspanTests(unittest.TestCase):
    def source(self, mode="normal"):
        doc, page, item = fixture(mode)
        self.addCleanup(doc.close)
        return page, item

    def test_closed_native_cell_restores_one_tier_only(self):
        page, item = self.source()
        before = copy.deepcopy(item)
        out = recover(item, page)
        self.assertIsNot(out, item)
        self.assertEqual(item, before)
        delta = next(c for c in out["data"]["table_cells"] if c["text"] == "Delta")
        self.assertEqual(
            (
                delta["start_row_offset_idx"],
                delta["end_row_offset_idx"],
                delta["row_span"],
            ),
            (1, 3, 2),
        )
        self.assertEqual(out["data"]["num_rows"], 7)
        self.assertEqual(
            [c for c in out["data"]["table_cells"] if not c["column_header"]],
            [c for c in item["data"]["table_cells"] if not c["column_header"]],
        )
        self.assertEqual(recover(out, page), out)

    def test_unproven_source_and_occupied_header_are_unchanged(self):
        for mode in [
            "crossing",
            "partial-crossing",
            "upper-nonempty",
            "annotation",
            "multiline",
            "wrong-row",
        ]:
            with self.subTest(mode=mode):
                page, item = self.source(mode)
                self.assertIs(recover(item, page), item)

    def test_rule_budget_and_ambiguous_physical_cells_abstain(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import layout_native_rowspans as module

        page, item = self.source()
        physical = module.physical_page(page)
        native = physical.find_tables()
        for edges, finder in (
            ([{}] * 801, lambda: self.fail("over-budget table search")),
            (physical.edges, lambda: native + native),
        ):
            with patch.object(
                module,
                "physical_page",
                return_value=SimpleNamespace(edges=edges, find_tables=finder),
            ):
                self.assertIs(recover(item, page), item)

    def test_unverified_text_annotation_in_upper_region_blocks_merge(self):
        from unittest.mock import PropertyMock, patch

        page, item = self.source()
        with patch.object(
            type(page),
            "annots",
            new_callable=PropertyMock,
            return_value=[
                {
                    "contents": "Additional visible text",
                    "x0": 350,
                    "x1": 390,
                    "top": 45,
                    "bottom": 55,
                }
            ],
        ):
            self.assertIs(recover(item, page), item)

    def test_malformed_annotations_edges_and_geometry_fail_closed(self):
        from types import SimpleNamespace
        from unittest.mock import PropertyMock, patch

        import layout_native_rowspans as module

        page, item = self.source()
        for annotation in (
            {"x0": 350, "x1": 390, "top": 45, "bottom": 55},
            {"contents": "", "x0": 350, "x1": 390, "top": 45, "bottom": 55},
            {"x0": float("nan"), "x1": 390, "top": 45, "bottom": 55},
            {"x0": "350", "x1": 390, "top": 45, "bottom": 55},
            {},
        ):
            with (
                self.subTest(annotation=annotation),
                patch.object(
                    type(page),
                    "annots",
                    new_callable=PropertyMock,
                    return_value=[annotation],
                ),
            ):
                self.assertIs(recover(item, page), item)
        physical = module.physical_page(page)
        for bad in (
            {"orientation": "h"},
            {
                "orientation": "h",
                "x0": 350,
                "x1": 390,
                "top": float("nan"),
                "bottom": 60,
            },
        ):
            with patch.object(
                module,
                "physical_page",
                return_value=SimpleNamespace(
                    edges=physical.edges + [bad],
                    find_tables=lambda: self.fail("invalid edges reached finder"),
                ),
            ):
                self.assertIs(recover(item, page), item)

        def fail():
            raise ValueError("invalid geometry")

        with patch.object(
            module,
            "physical_page",
            return_value=SimpleNamespace(edges=physical.edges, find_tables=fail),
        ):
            self.assertIs(recover(item, page), item)
        for bad in (None, (0, 1), (0, "1", 100, 100), (0, float("nan"), 100, 100)):
            with (
                patch.object(
                    module,
                    "physical_page",
                    return_value=SimpleNamespace(
                        edges=physical.edges,
                        find_tables=lambda bad=bad: [SimpleNamespace(cells=[bad])],
                    ),
                ),
                self.subTest(native_cell=bad),
            ):
                self.assertIs(recover(item, page), item)

    def test_real_annotation_appearance_without_contents_blocks_merge(self):
        from pypdf.generic import (
            ArrayObject,
            DecodedStreamObject,
            DictionaryObject,
            NameObject,
            NumberObject,
            TextStringObject,
        )

        for mode in ("empty", "missing"):
            doc, _page, item = fixture()
            self.addCleanup(doc.close)
            doc.stream.seek(0)
            writer = PdfWriter(clone_from=doc.stream)
            annotation = FreeText(text="Extra", rect=(350, 345, 390, 355))
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            appearance = DecodedStreamObject()
            appearance.set_data(b"BT /F1 10 Tf 0 2 Td (Extra) Tj ET")
            appearance.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Form"),
                    NameObject("/BBox"): ArrayObject(
                        [NumberObject(v) for v in (0, 0, 40, 10)]
                    ),
                    NameObject("/Resources"): DictionaryObject(
                        {
                            NameObject("/Font"): DictionaryObject(
                                {NameObject("/F1"): font}
                            )
                        }
                    ),
                }
            )
            annotation[NameObject("/AP")] = DictionaryObject(
                {NameObject("/N"): writer._add_object(appearance)}
            )
            if mode == "empty":
                annotation[NameObject("/Contents")] = TextStringObject("")
            else:
                del annotation["/Contents"]
            writer.add_annotation(0, annotation)
            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)
            with pdfplumber.open(buf) as annotated, self.subTest(mode=mode):
                self.assertTrue(annotated.pages[0].annots[0]["data"]["AP"])
                self.assertIs(recover(item, annotated.pages[0]), item)

    def test_crop_rotation_and_ambiguous_indices_are_rejected(self):
        for mode in ["crop", "rotation", "duplicate", "span"]:
            page, item = self.source()
            if mode == "crop":
                page.cropbox = (40, 0, 450, 400)
            elif mode == "rotation":
                page.rotation = 90
            elif mode == "duplicate":
                item["data"]["table_cells"].append(
                    copy.deepcopy(item["data"]["table_cells"][0])
                )
            else:
                item["data"]["table_cells"][4]["col_span"] = 2
            with self.subTest(mode=mode):
                self.assertIs(recover(item, page), item)


if __name__ == "__main__":
    unittest.main()
