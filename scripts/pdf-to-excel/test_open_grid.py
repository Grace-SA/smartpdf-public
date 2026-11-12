import io, sys, unittest, copy
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_open import recover_open_grid as repair
from layout_tables import local_box


class OpenTests(unittest.TestCase):
    def fixture(self, lines=True):
        stream = io.BytesIO()
        p = canvas.Canvas(stream, pagesize=(400, 400))
        p.setFont("Helvetica", 9)
        xs = [30, 100, 160, 220, 280, 340]
        ys = [350, 330, 310, 290, 270, 250, 230]
        if lines:
            for y in ys:
                p.line(100 if y >= 330 else 30, y, 340, y)
            # Physical interior dividers; both outside borders are intentionally absent.
            for i, x in enumerate(xs[1:-1], 1):
                p.line(x, 230, x, 350 if i in (1, 3) else 330)
        values = [["", "Group A", "", "Group B", ""], ["", "A", "B", "C", "D"]] + [
            [str(2000 + r), "1.1", "2.2", "3.3", "4.4"] for r in range(4)
        ]
        for r, row in enumerate(values):
            for c, value in enumerate(row):
                p.drawString(xs[c] + 3, ys[r] - 14, value)
        p.save()
        stream.seek(0)
        return pdfplumber.open(stream), values

    def item(self, page, values):
        cells = []
        for r, row in enumerate(values):
            for c, text in enumerate(row):
                if not text:
                    continue
                cs = 2 if r == 0 else 1
                cells.append(
                    dict(
                        text=text,
                        start_row_offset_idx=r,
                        end_row_offset_idx=r + 1,
                        start_col_offset_idx=c,
                        end_col_offset_idx=c + cs,
                        row_span=1,
                        col_span=cs,
                        bbox=None,
                    )
                )
        return dict(
            prov=[dict(bbox=local_box([29, 49, 341, 171], page))],
            data=dict(num_rows=6, num_cols=5, table_cells=cells),
        )

    def test_open_frame_recovers_empty_stub_and_grouped_headers(self):
        doc, values = self.fixture()
        with doc:
            item = self.item(doc.pages[0], values)
            out = repair(item, doc.pages[0])
            self.assertIsNotNone(out)
            self.assertEqual(len(out["heights"]), 6)
            self.assertEqual(len(out["widths"]), 5)
            self.assertEqual(
                [
                    (c["text"], c["cs"])
                    for c in sorted(out["cells"], key=lambda c: c["c"])
                    if c["r"] == 0 and c["text"]
                ],
                [("Group A", 2), ("Group B", 2)],
            )

    def test_changed_value_and_unruled_page_do_not_replace_model(self):
        doc, values = self.fixture()
        with doc:
            item = self.item(doc.pages[0], values)
            item["data"]["table_cells"][-1]["text"] = "4.5"
            self.assertIsNone(repair(item, doc.pages[0]))
        doc, values = self.fixture(False)
        with doc:
            item = self.item(doc.pages[0], values)
            self.assertIsNone(repair(item, doc.pages[0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
