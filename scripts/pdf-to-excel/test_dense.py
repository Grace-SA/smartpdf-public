import io, sys, unittest, copy
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_dense import dense_grid
from convert import ruled_tables


class DenseTests(unittest.TestCase):
    def fixture(self, extra_table=False):
        stream = io.BytesIO()
        p = canvas.Canvas(stream, pagesize=(600, 800))
        p.setFont("Helvetica", 8)
        xs = [20 + 90 * i for i in range(7)]
        ys = [760 - 27 * i for i in range(27)]
        for x in xs:
            p.line(x, ys[-1], x, ys[0])
        for y in ys:
            p.line(xs[0], y, xs[-1], y)
        rows = [["Name", "Place", "Date", "Count", "Amount", "Status"]] + [
            [f"Item {r}", "Town", "2024-05-01", f"{r:05}", "1.00", "Active"]
            for r in range(25)
        ]
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                p.drawString(xs[c] + 3, ys[r] - 16, text)
        if extra_table:
            p.setFont("Helvetica", 5)
            for r in range(3):
                p.drawString(30, 795 - r * 10, f"Extra{r}")
                p.drawString(150, 795 - r * 10, str(r + 1))
        p.save()
        stream.seek(0)
        return pdfplumber.open(stream)

    def test_closed_dense_grid_can_bypass_model_without_rewriting_values(self):
        with self.fixture() as pdf:
            tables = ruled_tables(pdf.pages[0])
            out = dense_grid(pdf.pages[0], tables)
            self.assertIsNotNone(out)
            self.assertEqual(out["cells"], tables[0]["cells"])
            self.assertTrue(any(c["text"] == "00001" for c in out["cells"]))

    def test_changed_number_sparse_grid_merges_or_missing_coverage_reject(self):
        with self.fixture() as pdf:
            page = pdf.pages[0]
            base = ruled_tables(page)
            variants = []
            a = copy.deepcopy(base)
            a[0]["cells"][10]["text"] = "99999"
            variants.append(a)
            a = copy.deepcopy(base)
            a[0]["closedGrid"] = False
            variants.append(a)
            a = copy.deepcopy(base)
            a[0]["cells"][10]["cs"] = 2
            variants.append(a)
            a = copy.deepcopy(base)
            a[0]["cells"] = a[0]["cells"][:-1]
            variants.append(a)
            for tables in variants:
                self.assertIsNone(dense_grid(page, tables))

    def test_separate_borderless_table_keeps_the_full_model_path(self):
        with self.fixture(extra_table=True) as pdf:
            page = pdf.pages[0]
            self.assertIsNone(dense_grid(page, ruled_tables(page)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
