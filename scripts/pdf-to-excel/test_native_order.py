"""Original source-order fixtures, not annotation-driven expected answers."""

import copy
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_native_order import recover


def fixture(lines=("7", "Level")):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(300, 300))
    c.setFont("Helvetica", 10)
    for i, line in enumerate(lines):
        c.drawString(50, 250 - i * 14, line)
    c.save()
    with pdfplumber.open(io.BytesIO(buf.getvalue())) as doc:
        chars = copy.deepcopy(doc.pages[0].chars)
    b = {
        "l": min(x["x0"] for x in chars),
        "t": min(x["top"] for x in chars) + 1,
        "r": max(x["x1"] for x in chars),
        "b": max(x["bottom"] for x in chars),
        "coord_origin": "TOPLEFT",
    }
    cell = {
        "text": " ".join(reversed(lines)),
        "bbox": b,
        "row_span": 1,
        "col_span": 1,
        "column_header": True,
        "start_row_offset_idx": 0,
        "start_col_offset_idx": 0,
        "end_row_offset_idx": 1,
        "end_col_offset_idx": 1,
    }
    page = SimpleNamespace(
        chars=chars,
        annots=[],
        bbox=(0, 0, 300, 300),
        cropbox=None,
        width=300,
        height=300,
        rotation=0,
    )
    return {"data": {"table_cells": [cell], "num_rows": 2, "num_cols": 2}}, page


class NativeOrderTests(unittest.TestCase):
    def test_literal_source_order_and_immutability(self):
        for lines in [
            ("7", "Level"),
            ("Start:", "June 12, 2024"),
            ("Alpha", "Beta", "Gamma"),
        ]:
            item, page = fixture(lines)
            before = copy.deepcopy(item)
            got = recover(item, page)
            self.assertEqual(got["data"]["table_cells"][0]["text"], "\n".join(lines))
            self.assertEqual(item, before)
            self.assertEqual(
                got["data"]["table_cells"][0]["bbox"],
                before["data"]["table_cells"][0]["bbox"],
            )

    def test_scope_multiset_and_unicode(self):
        for field, value in [
            ("column_header", False),
            ("row_span", 2),
            ("col_span", 2),
            ("text", "Level 8"),
            ("text", "Level Level 7"),
            ("text", "Level \u202e7"),
            ("text", "مستوى 7"),
            ("text", "等级 7"),
        ]:
            item, page = fixture()
            item["data"]["table_cells"][0][field] = value
            with self.subTest(field=field, value=value):
                self.assertIs(recover(item, page), item)
        item, page = fixture()
        item["data"]["table_cells"][0]["text"] = "7 Level"
        self.assertIs(recover(item, page), item)

    def test_geometry_font_and_direction(self):
        for field, value in [
            ("size", 5),
            ("size", float("nan")),
            ("fontname", "Other"),
            ("upright", False),
            ("matrix", (1, 0.1, 0, 1, 50, 250)),
            ("matrix", (1, 0, 0, 1, 50, float("nan"))),
            ("top", float("nan")),
        ]:
            item, page = fixture()
            page.chars[0][field] = value
            with self.subTest(field=field, value=value):
                self.assertIs(recover(item, page), item)
        for delta in [1.6, 10]:
            item, page = fixture()
            item["data"]["table_cells"][0]["bbox"]["t"] += delta
            self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.rotation = 90
        self.assertIs(recover(item, page), item)

    def test_crop_extra_glyph_and_ownership(self):
        item, page = fixture()
        page.cropbox = (0, 44, 300, 300)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        extra = copy.deepcopy(page.chars[0])
        extra["top"] -= 2
        extra["bottom"] = page.chars[0]["top"] + 0.1
        page.chars.append(extra)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        other = copy.deepcopy(item["data"]["table_cells"][0])
        other["column_header"] = False
        other["start_col_offset_idx"] = 1
        other["end_col_offset_idx"] = 2
        item["data"]["table_cells"].append(other)
        self.assertIs(recover(item, page), item)

    def test_annotation_including_empty_appearance_and_malformed(self):
        for annot in [
            {
                "x0": 49,
                "top": 40,
                "x1": 60,
                "bottom": 70,
                "contents": "",
                "data": {"AP": {}},
            },
            {"x0": 49, "top": 40, "x1": 60, "bottom": 70},
            {"x0": float("nan"), "top": 40, "x1": 60, "bottom": 70},
            {},
            {"x0": "49", "top": 40, "x1": 60, "bottom": 70},
        ]:
            item, page = fixture()
            page.annots = [annot]
            self.assertIs(recover(item, page), item)

    def test_size_tolerance_overlap_and_neighbor_are_conservative(self):
        item, page = fixture()
        # At 10 pt the allowance is 1.5 pt, not an unrestricted box expansion.
        item["data"]["table_cells"][0]["bbox"]["t"] += 0.51
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        # A small numeral beside another baseline is not a normal multiline header.
        page.chars[0]["size"] = 6
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        for c in page.chars[1:]:
            c["top"] -= 7
            c["bottom"] -= 7
            c["matrix"] = (*c["matrix"][:5], c["matrix"][5] + 7)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        # A competing cell claims the numeral only, not the complete candidate.
        other = copy.deepcopy(item["data"]["table_cells"][0])
        other["column_header"] = False
        other["start_col_offset_idx"] = 1
        other["end_col_offset_idx"] = 2
        other["bbox"]["b"] = page.chars[0]["bottom"]
        item["data"]["table_cells"].append(other)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.annots = [{"x0": 200, "top": 200, "x1": 210, "bottom": 210}]
        self.assertIsNot(recover(item, page), item)

    def test_malformed_structure_keeps_original(self):
        for key, value in [
            ("start_row_offset_idx", -1),
            ("end_row_offset_idx", 4),
            ("start_col_offset_idx", -1),
            ("end_col_offset_idx", 3),
            ("end_row_offset_idx", 0),
            ("end_col_offset_idx", 2),
            ("row_span", True),
            ("col_span", "1"),
            ("start_row_offset_idx", None),
        ]:
            item, page = fixture()
            item["data"]["table_cells"][0][key] = value
            with self.subTest(key=key, value=value):
                self.assertIs(recover(item, page), item)
        for key in ["num_rows", "num_cols"]:
            for value in [None, True, "2", 0, -1, 10001]:
                item, page = fixture()
                item["data"][key] = value
                self.assertIs(recover(item, page), item)
        item, page = fixture()
        item["data"]["table_cells"].append(
            copy.deepcopy(item["data"]["table_cells"][0])
        )
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        other = copy.deepcopy(item["data"]["table_cells"][0])
        other.update(row_span=2, end_row_offset_idx=2)
        item["data"]["table_cells"].append(other)
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        del item["data"]["table_cells"][0]["end_row_offset_idx"]
        self.assertIs(recover(item, page), item)

    def test_images_require_unambiguous_native_evidence(self):
        for image in [
            {"x0": 40, "top": 30, "x1": 100, "bottom": 100},
            {},
            {"x0": float("nan"), "top": 30, "x1": 100, "bottom": 100},
            {"x0": "40", "top": 30, "x1": 100, "bottom": 100},
        ]:
            item, page = fixture()
            page.images = [image]
            self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.images = [{"x0": 200, "top": 200, "x1": 210, "bottom": 210}]
        self.assertEqual(
            recover(item, page)["data"]["table_cells"][0]["text"], "7\nLevel"
        )

    def test_baselines_overlap_and_budgets(self):
        for shift in [6, 30]:
            item, page = fixture()
            for c in page.chars[1:]:
                c["matrix"] = (*c["matrix"][:5], c["matrix"][5] + shift)
            self.assertIs(recover(item, page), item)
        item, page = fixture()
        page.chars *= 25001
        self.assertIs(recover(item, page), item)
        item, page = fixture()
        item["data"]["table_cells"] *= 121
        self.assertIs(recover(item, page), item)


if __name__ == "__main__":
    unittest.main()
