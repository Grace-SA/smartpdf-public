import io, sys, unittest, copy
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_blank import restore_blank_merges
from convert import ruled_tables


def fixture(divider=False):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(400, 800))
    c.setFont("Helvetica", 9)
    for y in [780, 760, 680, 660]:
        c.line(40, y, 320, y)
    for x in [40, 320]:
        c.line(x, 660, x, 780)
    c.line(120, 680, 120, 760)
    c.line(220, 680, 220, 740)
    c.line(120, 740, 320, 740)
    for y in [720, 700]:
        c.line(40, y, 320, y)
    if divider:
        c.line(40, 740, 120, 740)
    for x, y, t in [
        (45, 766, "Outside title"),
        (45, 666, "Outside note"),
        (125, 746, "Quarter"),
        (125, 726, "East"),
        (225, 726, "West"),
        (45, 706, "One"),
        (125, 706, "10"),
        (225, 706, "20"),
        (45, 686, "Two"),
        (125, 686, "30"),
        (225, 686, "40"),
    ]:
        c.drawString(x, y, t)
    c.save()
    return buf.getvalue()


def model():
    cells = [
        dict(r=r, c=c, rs=1, cs=cs, text=text)
        for r, c, cs, text in [
            (0, 1, 2, "Quarter"),
            (1, 1, 1, "East"),
            (1, 2, 1, "West"),
            (2, 0, 1, "One"),
            (2, 1, 1, "10"),
            (2, 2, 1, "20"),
            (3, 0, 1, "Two"),
            (3, 1, 1, "30"),
            (3, 2, 1, "40"),
        ]
    ]
    return dict(
        bbox=[40, 40, 320, 120],
        widths=[80, 100, 100],
        heights=[20] * 4,
        cells=cells,
        method="layout",
    )


class BlankMerges(unittest.TestCase):
    def test_actual_source_borders_restore_omitted_blank_header(self):
        t = model()
        before = copy.deepcopy(t)
        with pdfplumber.open(io.BytesIO(fixture())) as pdf:
            o = restore_blank_merges(t, pdf.pages[0], ruled_tables)
        self.assertEqual(t, before)
        self.assertEqual([c for c in o["cells"] if c["text"]], t["cells"])
        self.assertEqual(
            [c for c in o["cells"] if not c["text"]],
            [dict(r=0, c=0, rs=2, cs=1, text="")],
        )
        self.assertEqual(o["widths"], t["widths"])
        self.assertEqual(o["heights"], t["heights"])

    def test_visible_divider_keeps_separate_empty_cells(self):
        t = model()
        with pdfplumber.open(io.BytesIO(fixture(True))) as pdf:
            self.assertIs(restore_blank_merges(t, pdf.pages[0], ruled_tables), t)

    def test_changed_number_and_wrong_populated_span_rejected(self):
        for change in ["text", "cs"]:
            t = model()
            t["cells"][-1][change] = "41" if change == "text" else 2
            with pdfplumber.open(io.BytesIO(fixture())) as pdf:
                self.assertIs(restore_blank_merges(t, pdf.pages[0], ruled_tables), t)

    def test_existing_blank_span_is_idempotent(self):
        t = model()
        t["cells"].append(dict(r=0, c=0, rs=2, cs=1, text=""))
        with pdfplumber.open(io.BytesIO(fixture())) as pdf:
            self.assertIs(restore_blank_merges(t, pdf.pages[0], ruled_tables), t)

    def test_crossing_empty_span_is_not_truncated(self):
        t = model()
        t["cells"].append(dict(r=0, c=0, rs=3, cs=1, text=""))
        with pdfplumber.open(io.BytesIO(fixture())) as pdf:
            self.assertIs(restore_blank_merges(t, pdf.pages[0], ruled_tables), t)

    def test_missing_bbox_and_nonfinite_rejected(self):
        for box in [None, [0, 0, float("nan"), 100], [0, 100, 100, 0]]:
            t = model()
            t["bbox"] = box
            with pdfplumber.open(io.BytesIO(fixture())) as pdf:
                self.assertIs(restore_blank_merges(t, pdf.pages[0], ruled_tables), t)


if __name__ == "__main__":
    unittest.main()
