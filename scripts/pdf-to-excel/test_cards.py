import sys, unittest, tempfile
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_cards import recover_card_tables
from convert import table_from_pdf


def card_tables(page):
    return recover_card_tables(page, table_from_pdf)


class CardTests(unittest.TestCase):
    def fixture(self, path, missing=False, borders=True):
        p = canvas.Canvas(str(path), pagesize=(600, 600))
        for r in range(5):
            for c in range(3):
                x, y = 20 + c * 185, 500 - r * 80
                if borders:
                    p.rect(x, y, 185, 80)
                p.rect(x + 143, y + 5, 38, 53)
                p.setFont("Helvetica", 8)
                p.drawString(x + 4, y + 67, f"{r*3+c+1:03}")
                p.drawString(x + 4, y + 52, "Name : Example Record")
                if not (missing and r == 2 and c == 1):
                    p.drawString(x + 4, y + 38, "Code : A001")
                if not (missing and r == 2 and c == 1):
                    p.drawString(x + 4, y + 10, "Region : North")
                p.setFont("Helvetica", 7)
                p.drawString(x + 4, y + 24, "Label")
                p.setFont("Helvetica", 9)
                p.drawString(x + 36, y + 25, ":Mixed font")
        p.save()

    def test_closed_repeated_cards_ignore_internal_portrait_boxes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cards.pdf"
            self.fixture(path)
            with pdfplumber.open(path) as doc:
                found = card_tables(doc.pages[0])
                self.assertEqual(len(found), 1)
                t = found[0]
                self.assertEqual((len(t["heights"]), len(t["widths"])), (5, 3))
                self.assertEqual(t["headerRows"], 0)
                for i, c in enumerate(t["cells"], 1):
                    self.assertIn(f"{i:03}", c["text"])
                    self.assertIn("Label :Mixed font", c["text"])

    def test_unclosed_or_insufficient_shared_fields_are_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            for label, args in [
                ("unclosed", dict(borders=False)),
                ("missing", dict(missing=True)),
            ]:
                path = Path(d) / f"{label}.pdf"
                self.fixture(path, **args)
                with pdfplumber.open(path) as doc:
                    self.assertEqual(card_tables(doc.pages[0]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
