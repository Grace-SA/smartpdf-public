import io, sys, unittest
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_dates import recover_date_tables


class DateTests(unittest.TestCase):
    def fixture(self, dates, overprint=True):
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        buf = io.BytesIO()
        p = canvas.Canvas(buf, pagesize=(400, 300))
        p.setFont("STSong-Light", 10)
        for i, (name, date) in enumerate(
            zip(["Address add", "Course book", "Degree good"], dates)
        ):
            for offset in ([0, 0.2] if overprint else [0]):
                p.drawString(30 + offset, 250 - i * 25, name)
                p.drawString(220 + offset, 250 - i * 25, date)
        p.save()
        buf.seek(0)
        return pdfplumber.open(buf)

    def test_overprinted_glyphs_recover_exact_dates_without_dropping_real_letters(self):
        dates = ["2019年05月", "2019年11月", "2020年02月"]
        with self.fixture(dates) as pdf:
            tables = recover_date_tables(pdf.pages[0])
        self.assertEqual(len(tables), 1)
        self.assertEqual(
            [c["text"] for c in tables[0]["cells"] if c["c"] == 0],
            ["Address add", "Course book", "Degree good"],
        )
        self.assertEqual([c["text"] for c in tables[0]["cells"] if c["c"] == 1], dates)
        self.assertEqual(tables[0]["headerRows"], 0)

    def test_invalid_month_or_prose_does_not_form_a_date_table(self):
        for value in ["2019年19月", "ordinary narrative"]:
            with self.fixture(["2019年05月", value, "2020年02月"], False) as pdf:
                self.assertEqual(recover_date_tables(pdf.pages[0]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
