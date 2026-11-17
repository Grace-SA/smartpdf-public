import io, sys, unittest
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_dense_rows import recover


def fixture(rows=16, broken=None, missing_separator=False, blank_block=False):
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(620, 792))
    c.setFont("Helvetica", 6)
    xs = [40 + i * 50 for i in range(11)]
    top = 720
    body = 694
    bottom = body - rows * 10
    for i, x in enumerate(xs):
        if missing_separator and i == 5:
            continue
        c.line(x, body, x, bottom)
        c.line(x, body, x, 704 if i not in (0, 1, 3, 6, 9, 10) else top)
    for y in [top, body, bottom] + [body - i * 10 for i in range(5, rows, 5)]:
        c.line(xs[0], y, xs[-1], y)
    for a, b, name in [(3, 6, "First Group"), (6, 9, "Second Group")]:
        c.drawCentredString((xs[a] + xs[b]) / 2, 710, name)
    for col in range(10):
        c.drawString(xs[col] + 2, 698, "ID" if col == 0 else "C" + str(col))
    expected = {}
    for row in range(rows):
        for col in range(10):
            text = "Record" + str(row) if col == 0 else str(1000 + row * 10 + col)
            if broken == (row, col):
                text = "unknown"
            if blank_block and row < 5 and col == 8:
                text = ""
            c.drawString(xs[col] + 2, body - 8 - row * 10, text)
            expected[(row + 2, col)] = text
    c.save()
    stream.seek(0)
    return stream, expected


class DenseRowsTests(unittest.TestCase):
    def test_coarse_rules_recover_every_record_and_header_merge(self):
        stream, expected = fixture()
        with pdfplumber.open(stream) as pdf:
            tables = recover(pdf.pages[0])
        self.assertEqual(len(tables), 1)
        t = tables[0]
        self.assertEqual((len(t["heights"]), len(t["widths"])), (18, 10))
        actual = {(c["r"], c["c"]): c["text"] for c in t["cells"] if c["r"] >= 2}
        self.assertEqual(actual, expected)
        self.assertIn(
            (0, 3, 1, 3, "First Group"),
            [(c["r"], c["c"], c["rs"], c["cs"], c["text"]) for c in t["cells"]],
        )
        self.assertTrue(all(h > 0 for h in t["heights"]))

    def test_non_numeric_row_breaks_complete_run(self):
        for row in [0, 7, 15]:
            with self.subTest(row=row):
                stream, _ = fixture(broken=(row, 5))
                with pdfplumber.open(stream) as pdf:
                    self.assertEqual(recover(pdf.pages[0]), [])

    def test_blank_physical_block_preserves_row_span(self):
        stream, _ = fixture(blank_block=True)
        with pdfplumber.open(stream) as pdf:
            tables = recover(pdf.pages[0])
        self.assertEqual(len(tables), 1)
        self.assertIn(
            (2, 8, 5, 1, ""),
            [(c["r"], c["c"], c["rs"], c["cs"], c["text"]) for c in tables[0]["cells"]],
        )

    def test_too_few_rows_not_admitted(self):
        stream, _ = fixture(rows=10)
        with pdfplumber.open(stream) as pdf:
            self.assertEqual(recover(pdf.pages[0]), [])

    def test_missing_boundary_must_not_merge_independent_numbers(self):
        stream, _ = fixture(missing_separator=True)
        with pdfplumber.open(stream) as pdf:
            self.assertEqual(recover(pdf.pages[0]), [])


class FragmentTests(unittest.TestCase):
    def test_only_covered_literal_fragments_are_replaced(self):
        from layout_dense_rows import replace_fragments
        import copy

        def cell(value):
            return dict(r=0, c=0, rs=1, cs=1, text=value)

        full = dict(bbox=[10, 10, 100, 100], cells=[cell("A"), cell("001"), cell("B")])
        fragment = dict(bbox=[20, 20, 80, 30], cells=[cell("001")])
        unrelated = dict(bbox=[150, 10, 250, 100], cells=[cell("Other")])
        self.assertEqual(
            replace_fragments([fragment, unrelated], [full]), [full, unrelated]
        )
        bad = copy.deepcopy(fragment)
        bad["cells"][0]["text"] = "002"
        self.assertEqual(replace_fragments([bad], [full]), [bad])
        crossed = copy.deepcopy(fragment)
        crossed["bbox"][2] = 120
        self.assertEqual(replace_fragments([crossed], [full]), [crossed])

    def test_cropped_away_header_is_not_recovered(self):
        stream, _ = fixture()
        with pdfplumber.open(stream) as pdf:
            self.assertEqual(recover(pdf.pages[0].crop((0, 105, 620, 792))), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
