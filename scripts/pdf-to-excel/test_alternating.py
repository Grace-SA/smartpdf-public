import io, sys, unittest
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_alternating import recover_alternating_tables as recover


class AlternatingTests(unittest.TestCase):
    def fixture(self, missing=False, ruled=True, font="Courier", partial=False):
        out = io.BytesIO()
        p = canvas.Canvas(out, pagesize=(800, 600))
        p.setFont(font, 8)
        a = [20, 120, 230, 450, 530, 580, 630]
        b = [20, 120, 230, 350]
        first = ["TYPE", "CLASS", "MAKER", "MODEL", "SIZE", "STATE", "FLAGS"]
        second = ["SERIAL", "TAG", "CASE", "LOCATION"]
        for x, t in zip(a, first):
            p.drawString(x, 550, t)
        for x, n in zip(a, [19, 21, 44, 15, 8, 9, 5]):
            if ruled:
                p.drawString(x, 542, "-" * n)
        for x, t in zip(b, second):
            p.drawString(x, 534, t)
        for x, n in zip(b, [13, 19, 20, 23]):
            if ruled:
                p.drawString(x, 526, "-" * n)
        for r in range(4):
            for j, (x, t) in enumerate(
                zip(
                    a,
                    [
                        "DEVICE",
                        "CLASS A",
                        "SYNTHETIC MAKER",
                        "MODEL A",
                        "001",
                        "READY",
                        "____",
                    ],
                )
            ):
                if partial and r == 3 and j > 1:
                    continue
                p.drawString(x, 510 - r * 24, t)
            if (missing or partial) and r == 3:
                continue
            for x, t in zip(b, [f"{r:05}", f"Tag {r:04}", f"CASE {r:05}", "STORAGE A"]):
                p.drawString(x, 502 - r * 24, t)
        p.save()
        out.seek(0)
        return pdfplumber.open(out)

    def test_two_field_patterns_keep_record_pairing_spans_and_literal_values(self):
        with self.fixture() as pdf:
            tables = recover(pdf.pages[0])
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual((len(table["heights"]), len(table["widths"])), (10, 8))
        cells = {(c["r"], c["c"]): c for c in table["cells"]}
        self.assertEqual(cells[(0, 2)]["cs"], 2)
        self.assertEqual(cells[(1, 3)]["cs"], 5)
        self.assertEqual(cells[(3, 0)]["text"], "00000")
        self.assertEqual(cells[(2, 7)]["text"], "____")

    def test_missing_record_line_missing_underlines_or_nonmonospace_font_reject(self):
        for kwargs in [
            dict(missing=True),
            dict(partial=True),
            dict(ruled=False),
            dict(font="Helvetica"),
        ]:
            with self.fixture(**kwargs) as pdf:
                self.assertEqual(recover(pdf.pages[0]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
