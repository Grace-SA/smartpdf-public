import copy
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook
from reportlab.pdfbase.pdfmetrics import stringWidth

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import readable_heights, write_workbook


class OutputMetricTests(unittest.TestCase):
    def table(self, family="Arial", bold=False, italic=False):
        return dict(
            page=1,
            index=1,
            widths=[63],
            heights=[14],
            headerRows=0,
            fontSize=11,
            sourceTypography=True,
            cells=[
                dict(
                    r=0,
                    c=0,
                    rs=1,
                    cs=1,
                    text="WWWWWWWW",
                    fontName=family,
                    fontSize=11,
                    bold=bold,
                    italic=italic,
                    sourceFont=True,
                    glyphWidths={"W": 5.0},
                )
            ],
        )

    def test_condensed_source_metrics_cannot_clip_wider_workbook_face(self):
        for family, face, bold, italic in [
            ("Arial", "Helvetica", False, False),
            ("Arial", "Helvetica-BoldOblique", True, True),
            ("Times New Roman", "Times-Bold", True, False),
            ("Courier New", "Courier-Oblique", False, True),
        ]:
            with self.subTest(family=family, face=face):
                table = self.table(family, bold, italic)
                width = 10 if family == "Courier New" else 12
                self.assertGreater(stringWidth("WWWWWWWW", face, 11), width * 5.25 - 4)
                before = copy.deepcopy(table)
                height = readable_heights(table, [width], 11)[0]
                self.assertGreaterEqual(height, 2 * 11 * 1.15 + 1)
                self.assertEqual(table, before)

    def test_unknown_face_and_uncompressed_source_keep_existing_geometry(self):
        unknown = self.table("Unknown face")
        self.assertEqual(readable_heights(unknown, [12], 11), [14])
        ordinary = self.table()
        ordinary["cells"][0]["glyphWidths"] = {"W": stringWidth("W", "Helvetica", 11)}
        ordinary["heights"] = [35]
        self.assertEqual(readable_heights(ordinary, [12], 11), [35])

    def test_export_keeps_literal_text_and_span_with_expanded_height(self):
        table = self.table()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "output.xlsx"
            write_workbook([table], target, "tables")
            book = load_workbook(target)
            try:
                self.assertEqual(book.active["A1"].value, "WWWWWWWW")
                self.assertEqual(book.active["A1"].font.name, "Arial")
                self.assertEqual(book.active["A1"].font.sz, 11)
                self.assertFalse(book.active.merged_cells.ranges)
                self.assertGreaterEqual(book.active.row_dimensions[1].height, 26.3)
            finally:
                book.close()
