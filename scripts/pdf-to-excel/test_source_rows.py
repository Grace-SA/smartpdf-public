import io, sys, copy, unittest, importlib.util
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

G = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(G / "server/pdf-to-excel"))
from layout_tables import local_box
import layout_source_rows as m


def fixture(rows=16, broken=None, boxed=False):
    stream = io.BytesIO()
    p = canvas.Canvas(stream, pagesize=(520, 500))
    p.setFont("Helvetica", 8)
    xs = [40, 120, 210, 300, 390]
    expected = {}
    header = ["Region", "2013–14", "2014–15", "2015–16", "2016–17"]
    for col, text in enumerate(header):
        p.drawString(xs[col], 460, text)
    for row in range(rows):
        for col in range(5):
            value = (
                "LongRegionW" + str(row) if col == 0 else str(10000 + row * 10 + col)
            )
            if (row, col) == broken:
                value = "unknown"
            expected[row + 1, col] = value
            p.drawString(xs[col], 444 - row * 12, value)
    if boxed:
        p.rect(35, 444 - (rows - 1) * 12 - 3, 430, (rows - 1) * 12 + 12)
        for x in [105, 195, 285, 375]:
            p.line(x, 444 - (rows - 1) * 12 - 3, x, 453)
    p.save()
    stream.seek(0)
    doc = pdfplumber.open(stream)
    page = doc.pages[0]
    cells = []

    def add(row, col, text, top, bottom, rs=1):
        right = 60 if col == 0 else xs[col] + 28
        cells.append(
            dict(
                start_row_offset_idx=row,
                end_row_offset_idx=row + rs,
                start_col_offset_idx=col,
                end_col_offset_idx=col + 1,
                row_span=rs,
                col_span=1,
                text=text,
                bbox=local_box([xs[col], top, right, bottom], page),
                column_header=row == 0,
                row_header=col == 0,
            )
        )

    for col, text in enumerate(header):
        add(0, col, text, 33, 42)
    for row in range(rows):
        if row == 7:
            continue
        for col in range(5):
            value = expected[row + 1, col]
            top = 49 + row * 12
            bottom = top + 9
            if row == 6:
                value += "\n" + expected[row + 2, col]
                bottom += 12
            add(row + 1 - int(row > 7), col, value, top, bottom)
    item = dict(
        prov=[dict(bbox=local_box([35, 31, 465, 49 + (rows - 1) * 12 + 11], page))],
        data=dict(num_rows=rows, num_cols=5, table_cells=cells),
    )
    return doc, page, item, expected


class SourceBodyTests(unittest.TestCase):
    def test_all_source_rows_and_overhanging_names_survive(self):
        doc, page, item, expected = fixture()
        try:
            original = copy.deepcopy(item)
            fixed = m.recover(item, page)
            self.assertIsNot(fixed, item)
            self.assertEqual(item, original)
            actual = {
                (c["start_row_offset_idx"], c["start_col_offset_idx"]): c["text"]
                for c in fixed["data"]["table_cells"]
                if c["start_row_offset_idx"] > 0
            }
            self.assertEqual(actual, expected)
            self.assertEqual(fixed["data"]["num_rows"], 17)
            self.assertEqual(
                sum(
                    c.get("column_header", False) for c in fixed["data"]["table_cells"]
                ),
                5,
            )
        finally:
            doc.close()

    def test_non_numeric_middle_row_does_not_get_dropped(self):
        doc, page, item, _ = fixture(broken=(7, 2))
        try:
            self.assertIs(m.recover(item, page), item)
        finally:
            doc.close()

    def test_multiline_box_is_not_split_into_records(self):
        doc, page, item, _ = fixture(boxed=True)
        try:
            self.assertIs(m.recover(item, page), item)
        finally:
            doc.close()

    def test_already_correct_rows_are_not_rewritten(self):
        doc, page, item, _ = fixture()
        try:
            fixed = m.recover(item, page)
            self.assertIs(m.recover(fixed, page), fixed)
        finally:
            doc.close()

    def test_short_runs_are_not_rebuilt(self):
        doc, page, item, _ = fixture(rows=10)
        try:
            self.assertIs(m.recover(item, page), item)
        finally:
            doc.close()

    def test_nonfinite_or_outside_model_bounds_are_rejected(self):
        doc, page, item, _ = fixture()
        try:
            for value in [float("nan"), -100]:
                changed = copy.deepcopy(item)
                changed["prov"][0]["bbox"]["l"] = value
                self.assertIs(m.recover(changed, page), changed)
        finally:
            doc.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
