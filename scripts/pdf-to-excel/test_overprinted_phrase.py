import io
from pathlib import Path
import sys
import unittest

import pdfplumber
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import ruled_tables
from source_glyphs import visible_glyphs


def fixture(phrase="Delta and Alpha", count=42, same_line=True, blank_first=True):
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(400, 200))
    for x in [20, 230, 380]:
        canvas.line(x, 40, x, 140)
    for y in [40, 90, 140]:
        canvas.line(20, y, 380, y)
    canvas.setFont("Times-Roman", 10)
    canvas.drawString(24, 120, "Location")
    canvas.drawString(234, 120, "Code")
    if blank_first:
        canvas.drawString(24, 70 if same_line else 55, " " * count)
    canvas.drawString(24, 70, phrase)
    if not blank_first:
        canvas.drawString(24, 70, " " * count)
    canvas.drawString(234, 70, "0012")
    canvas.save()
    stream.seek(0)
    return pdfplumber.open(stream)


class OverprintedPhraseTests(unittest.TestCase):
    def test_long_earlier_blank_run_keeps_source_word_boundaries_and_all_ink(self):
        with fixture() as doc:
            page = doc.pages[0]
            before = page.chars
            after = visible_glyphs(before)
            self.assertLess(len(after), len(before))
            self.assertEqual(
                [c for c in before if c["text"].strip()],
                [c for c in after if c["text"].strip()],
            )
            table = ruled_tables(page)[0]
            self.assertEqual(
                next(c["text"] for c in table["cells"] if (c["r"], c["c"]) == (1, 0)),
                "Delta and Alpha",
            )
            self.assertEqual(
                next(c["text"] for c in table["cells"] if (c["r"], c["c"]) == (1, 1)),
                "0012",
            )

    def test_single_blank_later_overlay_and_other_line_keep_original_glyphs(self):
        for options in [
            dict(count=1),
            dict(blank_first=False),
            dict(same_line=False),
            dict(phrase="Delta Alpha"),
        ]:
            with self.subTest(options=options), fixture(**options) as doc:
                chars = doc.pages[0].chars
                self.assertEqual(visible_glyphs(chars), chars)

    def test_intentionally_spaced_letters_and_real_word_gaps_are_not_joined(self):
        with fixture(phrase="A B C D E") as doc:
            table = ruled_tables(doc.pages[0])[0]
            value = next(
                c["text"] for c in table["cells"] if (c["r"], c["c"]) == (1, 0)
            )
            self.assertEqual(value, "A B C D E")
