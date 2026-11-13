import io
import sys
import unittest
from pathlib import Path

import pdfplumber
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_tables import source_cell_text
from source_phrases import restore_line_order


class SourceLineOrderTests(unittest.TestCase):
    def test_visual_order_overrides_reversed_content_stream_without_rewriting_values(
        self,
    ):
        stream = io.BytesIO()
        c = Canvas(stream, pagesize=(300, 200))
        c.setFont("Helvetica", 12)
        c.drawString(40, 120, "May 21, 2009")
        c.drawString(40, 145, "Launch:")
        c.save()
        with pdfplumber.open(stream) as doc:
            box = dict(l=38, t=42, r=130, b=83, coord_origin="TOPLEFT")
            self.assertEqual(
                source_cell_text("May 21, 2009 Launch:", box, doc.pages[0]),
                "Launch: May 21, 2009",
            )
            self.assertEqual(
                source_cell_text("May 21, 2019 Launch:", box, doc.pages[0]),
                "May 21, 2019 Launch:",
            )

    def test_complete_unique_lines_are_required(self):
        chars = [
            dict(text="x", size=12, x0=40, x1=70, top=y, bottom=y + 12)
            for y in [10, 30]
        ]
        self.assertEqual(
            restore_line_order("Second\nFirst", "First\nSecond", chars), "First\nSecond"
        )
        self.assertEqual(restore_line_order("Grade 3", "3\nGrade", chars), "3 Grade")
        for text, original in [
            ("Second First extra", "First\nSecond"),
            ("Second First", "First Second"),
            ("Second First First", "First\nFirst\nSecond"),
            ("3 1", "1\n3"),
            ("First Second", "First\nSecond"),
            ("Second altered First", "First\nSecond value"),
            ("E D C B A", "A\nB\nC\nD\nE"),
        ]:
            with self.subTest(text=text, original=original):
                self.assertIsNone(restore_line_order(text, original, chars))

    def test_mixed_size_markers_and_missing_font_evidence_abstain(self):
        for chars in [
            [],
            [dict(text="x", size=None)],
            [dict(text="x", size=float("nan"))],
            [dict(text="x", size=12), dict(text="1", size=6)],
        ]:
            self.assertIsNone(
                restore_line_order("Second First", "First\nSecond", chars)
            )

    def test_disjoint_columns_do_not_become_a_reordered_phrase(self):
        stream = io.BytesIO()
        c = Canvas(stream, pagesize=(300, 200))
        c.setFont("Helvetica", 12)
        c.drawString(150, 145, "Marker")
        c.drawString(40, 120, "District")
        c.save()
        with pdfplumber.open(stream) as doc:
            page = doc.pages[0]
            self.assertIsNone(
                restore_line_order("District Marker", "Marker\nDistrict", page.chars)
            )
            self.assertEqual(
                source_cell_text(
                    "District Marker",
                    dict(l=38, t=42, r=200, b=83, coord_origin="TOPLEFT"),
                    page,
                ),
                "District Marker",
            )

    def test_missing_nonfinite_and_inconsistent_line_geometry_abstain(self):
        valid = [
            dict(text="x", size=12, x0=40, x1=70, top=y, bottom=y + 12)
            for y in [10, 30]
        ]
        for chars in [
            [dict(text="x", size=12)],
            [dict(valid[0], x0=float("nan")), valid[1]],
            [valid[0]],
            [valid[0], dict(valid[1], top=10, bottom=22)],
        ]:
            with self.subTest(chars=chars):
                self.assertIsNone(
                    restore_line_order("Second First", "First\nSecond", chars)
                )
