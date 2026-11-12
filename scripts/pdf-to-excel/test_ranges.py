import sys, tempfile, unittest
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_tables import source_cell_text
from layout_tables import local_box


class RangeTests(unittest.TestCase):
    def test_visible_separation_preserves_parser_spacing_without_changing_digits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ranges.pdf"
            p = canvas.Canvas(str(path), pagesize=(300, 300))
            p.setFont("Helvetica", 10)
            x = 40
            p.drawString(x, 240, "10")
            x += stringWidth("10", "Helvetica", 10) + 1.5
            p.drawString(x, 240, "–")
            x += stringWidth("–", "Helvetica", 10) + 2.5
            p.drawString(x, 240, "20")
            p.drawString(40, 210, "10–20")
            p.save()
            with pdfplumber.open(path) as doc:
                page = doc.pages[0]
                box = local_box([39, 50, 90, 65], page)
                self.assertEqual(source_cell_text("10 - 20", box, page), "10 – 20")
                self.assertEqual(source_cell_text("10 - 21", box, page), "10 - 21")
                tight = local_box([39, 80, 90, 95], page)
                self.assertEqual(source_cell_text("10 - 20", tight, page), "10–20")


if __name__ == "__main__":
    unittest.main(verbosity=2)
