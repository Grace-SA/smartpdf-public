import io, sys, unittest
from pathlib import Path
from collections import Counter
from types import SimpleNamespace
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_forms import recover, checkboxes, horizontal_rules


def fixture(mark="cross", count=6):
    b = io.BytesIO()
    p = canvas.Canvas(b, pagesize=(400, 400))
    p.setFont("Helvetica-Bold", 12)
    p.drawString(30, 360, "Account summary")
    p.setFont("Helvetica", 10)
    for i in range(count):
        y = 320 - i * 25
        p.rect(30, y, 9, 9)
        p.drawString(45, y, "Choice " + str(i))
        if i % 2 == 0:
            if mark == "cross":
                p.line(30, y, 39, y + 9)
                p.line(30, y + 9, 39, y)
            if mark == "partial":
                p.line(30, y, 39, y + 9)
            if mark == "tick":
                p.line(32, y + 5, 34, y + 3)
                p.line(34, y + 3, 37, y + 7)
    p.save()
    b.seek(0)
    return b


class FormTests(unittest.TestCase):
    def test_every_text_character_and_checkbox_preserved(self):
        with pdfplumber.open(fixture()) as d:
            p = d.pages[0]
            t = recover(p)
            self.assertIsNotNone(t)
            self.assertEqual((t["checkboxCount"], t["checkedCount"]), (6, 3))
            source = Counter(
                ch for c in p.chars for ch in c["text"] if not ch.isspace()
            )
            actual = Counter(
                ch
                for c in t["cells"]
                if not c.get("checkbox")
                for ch in c["text"]
                if not ch.isspace()
            )
            self.assertEqual(actual, source)
            self.assertTrue(all(h > 0 for h in t["heights"]))
            self.assertTrue(
                all(
                    c["r"] + c["rs"] <= len(t["heights"])
                    and c["c"] + c["cs"] <= len(t["widths"])
                    for c in t["cells"]
                )
            )

    def test_ambiguous_marks_are_not_silently_unchecked(self):
        for mark in ["partial", "tick"]:
            with self.subTest(mark=mark), pdfplumber.open(fixture(mark=mark)) as d:
                self.assertIsNone(recover(d.pages[0]))

    def test_insufficient_form_evidence_rejected(self):
        with pdfplumber.open(fixture(count=2)) as d:
            self.assertIsNone(recover(d.pages[0]))

    def test_rules_clip_to_view_and_do_not_turn_white_fills_black(self):
        base = dict(x0=10, x1=180, top=40, bottom=41, width=170, height=1, fill=True)
        page = SimpleNamespace(
            rects=[
                dict(base, non_stroking_color=0),
                dict(base, top=50, bottom=51, non_stroking_color=1),
            ]
        )
        self.assertEqual(
            horizontal_rules(page, [20, 0, 160, 100]),
            [dict(x0=20, x1=160, y=40.5, weight=1)],
        )

    def test_outside_crop_checkboxes_not_counted(self):
        with pdfplumber.open(fixture()) as d:
            p = d.pages[0]
            p.cropbox = (100, 0, 400, 400)
            self.assertEqual(checkboxes(p), [])
            self.assertIsNone(recover(p))


if __name__ == "__main__":
    unittest.main(verbosity=2)
