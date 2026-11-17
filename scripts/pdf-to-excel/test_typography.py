import unittest, tempfile, sys, copy
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas
from pdfplumber.utils import extract_text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import ruled_tables
from layout_typography import apply_source_typography as attach
from source_glyphs import visible_glyphs as visible_chars


class TypographyTests(unittest.TestCase):
    def test_multiline_header_font_requires_complete_ordered_source_phrase(self):
        from layout_typography import readable_header_widths

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "overhanging-header.pdf"
            p = canvas.Canvas(str(path), pagesize=(260, 220))
            p.setFont("Helvetica", 8)
            p.drawString(152, 150, "School participation")
            p.drawString(152, 135, "response rate")
            p.save()
            cell = dict(
                r=0,
                c=1,
                rs=1,
                cs=1,
                text="School participation response rate",
                sourceTextCandidate=[153, 62, 224, 80],
            )
            base = dict(
                bbox=[30, 60, 230, 120],
                widths=[140, 60],
                heights=[22, 38],
                headerRows=1,
                sourceGeometry=True,
                cells=[cell],
            )
            with pdfplumber.open(path) as source:
                table = copy.deepcopy(base)
                self.assertEqual(attach(table, source.pages[0]), 1)
                self.assertEqual(table["cells"][0]["fontName"], "Arial")
                self.assertEqual(table["cells"][0]["fontSize"], 8)
                self.assertFalse(table["cells"][0]["bold"])
                self.assertEqual(table["cells"][0]["text"], cell["text"])
                self.assertEqual(table["widths"], base["widths"])
                for text, box in [
                    ("School response participation rate", cell["sourceTextCandidate"]),
                    (
                        "School participation response rates",
                        cell["sourceTextCandidate"],
                    ),
                    (cell["text"], [20, 62, 100, 80]),
                    (cell["text"], [153, float("nan"), 224, 80]),
                ]:
                    bad = copy.deepcopy(base)
                    bad["cells"][0].update(text=text, sourceTextCandidate=box)
                    self.assertEqual(attach(bad, source.pages[0]), 0)
                    self.assertNotIn("sourceFont", bad["cells"][0])

    def fixture(self, path):
        p = canvas.Canvas(str(path), pagesize=(300, 300))
        for y in [180, 200, 220, 240]:
            p.line(30, y, 200, y)
        for x in [30, 70, 200]:
            p.line(x, 180, x, 240)
        p.setFont("Times-Bold", 8)
        p.drawString(32, 228, "Female")
        p.drawString(73, 228, "Group")
        p.setFont("Times-Roman", 10)
        p.drawString(32, 208, "12.34")
        p.drawString(73, 208, "Unit One")
        p.drawString(32, 188, "98.76")
        p.drawString(73, 188, "Unit Two")
        p.save()

    def test_source_font_size_and_changed_number_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "table.pdf"
            self.fixture(path)
            with pdfplumber.open(path) as pdf:
                t = ruled_tables(pdf.pages[0])[0]
                bad = copy.deepcopy(t)
                next(c for c in bad["cells"] if c["text"] == "12.34")["text"] = "99.99"
                self.assertEqual(attach(t, pdf.pages[0]), 6)
                header = next(c for c in t["cells"] if c["text"] == "Female")
                self.assertEqual(header["fontName"], "Times New Roman")
                self.assertAlmostEqual(header["fontSize"], 8)
                self.assertTrue(header["bold"])
                self.assertEqual(attach(bad, pdf.pages[0]), 5)

    def test_native_grid_and_workbook_preserve_visible_values_and_source_sizes(self):
        from convert import write_workbook
        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "grid.pdf"
            pdf = canvas.Canvas(str(path), pagesize=(300, 300))
            for y in [180, 200, 220, 240]:
                pdf.line(30, y, 220, y)
            for x in [30, 130, 220]:
                pdf.line(x, 180, x, 240)
            pdf.setFont("Times-Bold", 8)
            pdf.drawString(32, 228, "Date")
            pdf.drawString(132, 228, "Group")
            pdf.setFont("Times-Roman", 10)
            pdf.drawString(32, 208, "                      ")
            pdf.drawString(32, 208, "03/25/2016")
            pdf.drawString(132, 208, "Unit One")
            pdf.drawString(32, 188, "04/26/2016")
            pdf.drawString(132, 188, "Unit Two")
            pdf.save()
            with pdfplumber.open(path) as source:
                table = ruled_tables(source.pages[0])[0]
                self.assertEqual(attach(table, source.pages[0]), 6)
            table.update(page=1, index=1)
            output = Path(temp) / "result.xlsx"
            write_workbook([table], output, "tables")
            book = load_workbook(output)
            try:
                self.assertEqual(
                    list(book.active.values),
                    [
                        ("Date", "Group"),
                        ("03/25/2016", "Unit One"),
                        ("04/26/2016", "Unit Two"),
                    ],
                )
                self.assertEqual(book.active["A1"].font.name, "Times New Roman")
                self.assertEqual(book.active["A1"].font.sz, 8)
                self.assertEqual(book.active["A2"].font.sz, 10)
                self.assertFalse(book.active["A2"].font.bold)
                self.assertEqual(book.active.row_dimensions[2].height, 20)
            finally:
                book.close()

    def test_unverified_font_transform_and_nonfinite_bounds_keep_fallback(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.pdf"
            self.fixture(path)
            with pdfplumber.open(path) as source:
                page = source.pages[0]
                table = ruled_tables(page)[0]
                for change in [
                    dict(matrix=(0.6, 0, 0, 1, 0, 0)),
                    dict(size=float("nan")),
                    dict(fontname="UnrecognizedEmbeddedFace"),
                ]:
                    fake = SimpleNamespace(
                        rotation=0, chars=[dict(c, **change) for c in page.chars]
                    )
                    candidate = copy.deepcopy(table)
                    self.assertEqual(attach(candidate, fake), 0)
                    self.assertNotIn("sourceTypography", candidate)
                table["bbox"][3] = float("inf")
                self.assertEqual(attach(table, page), 0)

    def test_overlay_whitespace_is_removed_but_normal_word_gap_remains(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "text.pdf"
            p = canvas.Canvas(str(path), pagesize=(300, 200))
            p.setFont("Helvetica", 10)
            p.drawString(30, 150, "                  ")
            p.drawString(30, 150, "03/25/2016")
            p.drawString(30, 120, "Unit One")
            p.drawString(30, 90, "1 2")
            p.save()
            with pdfplumber.open(path) as pdf:
                before = pdf.pages[0].chars
                after = visible_chars(before)
                self.assertLess(len(after), len(before))
                text = extract_text(after, x_tolerance=2, y_tolerance=3)
                self.assertIn("03/25/2016", text)
                self.assertIn("Unit One", text)
                self.assertIn("1 2", text)
                self.assertEqual(
                    [c for c in before if c["text"].strip()],
                    [c for c in after if c["text"].strip()],
                )

    def test_rotated_whitespace_and_separate_line_not_removed(self):
        base = dict(text="X", x0=10, x1=20, top=10, bottom=20, upright=True)
        blank = dict(base, text=" ", upright=False)
        other = dict(base, text=" ", top=25, bottom=35)
        self.assertEqual(visible_chars([base, blank, other]), [base, blank, other])
        for bounds in [
            dict(top=float("nan")),
            dict(bottom=1e100),
            dict(x0=float("inf")),
            dict(top=21, bottom=20),
        ]:
            invalid = dict(base, text=" ", **bounds)
            self.assertEqual(visible_chars([base, invalid]), [base, invalid])

    def test_overhanging_words_and_leaders_keep_their_spaces(self):
        # Kerning, RTL joining and dot leaders can put a visible glyph over a
        # real word separator. Overlap alone must never join those words.
        for text in ["abc", "حزب", "...19", "19", "ba-9", "xxiii.Acute"]:
            chars = [
                dict(
                    text=ch,
                    x0=10 + i * 5,
                    x1=15 + i * 5,
                    top=10,
                    bottom=20,
                    upright=True,
                )
                for i, ch in enumerate(text)
            ]
            blank = dict(chars[1], text=" ")
            source = [*chars, blank]
            self.assertEqual(visible_chars(source), source)
        chars = [
            dict(text=ch, x0=10 + i * 5, x1=15 + i * 5, top=10, bottom=20, upright=True)
            for i, ch in enumerate("123")
        ]
        blank = dict(chars[1], text=" ")
        self.assertEqual(visible_chars([*chars, blank]), chars)

    def test_verified_narrow_header_word_gets_bounded_padding(self):
        from layout_typography import readable_header_widths
        from convert import write_workbook
        from openpyxl import load_workbook

        table = dict(
            page=1,
            index=1,
            widths=[24, 80],
            heights=[12, 12],
            headerRows=1,
            sourceGeometry=True,
            cells=[
                dict(
                    r=0,
                    c=0,
                    rs=1,
                    cs=1,
                    text="FLAGS",
                    sourceFont=True,
                    fontName="Courier New",
                    fontSize=8,
                    glyphWidths={ch: 4.8 for ch in "FLAGS"},
                ),
                dict(
                    r=0,
                    c=1,
                    rs=1,
                    cs=1,
                    text="Group",
                    sourceFont=True,
                    fontName="Courier New",
                    fontSize=8,
                    glyphWidths={ch: 4.8 for ch in "Group"},
                ),
                dict(r=1, c=0, rs=1, cs=1, text="001"),
                dict(r=1, c=1, rs=1, cs=1, text="Unit One"),
            ],
        )
        before = copy.deepcopy(table)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "header.xlsx"
            write_workbook([table], output, "tables")
            book = load_workbook(output)
            try:
                self.assertEqual(
                    list(book.active.values), [("FLAGS", "Group"), ("001", "Unit One")]
                )
                self.assertGreaterEqual(
                    book.active.column_dimensions["A"].width * 5.25, 28
                )
                self.assertLess(book.active.row_dimensions[1].height, 15)
                self.assertFalse(book.active.merged_cells.ranges)
            finally:
                book.close()
        self.assertEqual(table, before)
        for change in [
            dict(sourceFont=False),
            dict(glyphWidths={}),
            dict(glyphWidths={ch: 40 for ch in "FLAGS"}),
            dict(rotation=90),
        ]:
            candidate = copy.deepcopy(table)
            candidate["cells"][0].update(change)
            self.assertEqual(readable_header_widths(candidate), table["widths"])


if __name__ == "__main__":
    unittest.main()
