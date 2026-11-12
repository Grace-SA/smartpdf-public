import sys, copy, tempfile, unittest
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_headers import restore_underlined_headers as repair
from layout_tables import local_box


class HeaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = Path(self.tmp.name) / "fixture.pdf"
        pdf = canvas.Canvas(str(p), pagesize=(300, 600))
        pdf.setFont("Helvetica", 10)
        for a, b in [(100, 175), (175, 250)]:
            pdf.line(a, 490, b, 490)
        for x, y, t in [
            (155, 500, "Actual"),
            (35, 475, "Region"),
            (110, 475, "2005–06"),
            (190, 475, "2006–07"),
        ]:
            pdf.drawString(x, y, t)
        for y, label in [(440, "East"), (410, "West"), (380, "South")]:
            for x, t in [(35, label), (110, "111"), (190, "222")]:
                pdf.drawString(x, y, t)
        pdf.save()
        self.doc = pdfplumber.open(p)
        self.page = self.doc.pages[0]
        words = self.page.extract_words()
        cells = []

        def word(text, top=None):
            return next(
                w
                for w in words
                if w["text"] == text and (top is None or abs(w["top"] - top) < 2)
            )

        def box(ws):
            return local_box(
                [
                    min(w["x0"] for w in ws),
                    min(w["top"] for w in ws),
                    max(w["x1"] for w in ws),
                    max(w["bottom"] for w in ws),
                ],
                self.page,
            )

        def cell(r, c, text, ws, header=False):
            return dict(
                start_row_offset_idx=r,
                end_row_offset_idx=r + 1,
                start_col_offset_idx=c,
                end_col_offset_idx=c + 1,
                row_span=1,
                col_span=1,
                text=text,
                bbox=box(ws),
                column_header=header,
            )

        cells = [
            cell(1, 0, "Region", [word("Region")], True),
            cell(1, 1, "Actual 2005-06", [word("Actual"), word("2005–06")], True),
            cell(1, 2, "2006-07", [word("2006–07")], True),
        ]
        for r, (y, label) in enumerate(
            [(440, "East"), (410, "West"), (380, "South")], 2
        ):
            for c, text in enumerate([label, "111", "222"]):
                cells.append(cell(r, c, text, [word(text, 600 - y - 8)]))
        self.item = dict(
            prov=[dict(bbox=local_box([30, 80, 250, 240], self.page))],
            data=dict(num_rows=5, num_cols=3, table_cells=cells),
        )

    def tearDown(self):
        self.doc.close()
        self.tmp.cleanup()

    def test_independent_header_rule_restores_span_and_separates_date(self):
        new = repair(self.item, self.page)
        cells = new["data"]["table_cells"]
        heading = next(c for c in cells if c["text"] == "Actual")
        self.assertEqual(
            (
                heading["start_row_offset_idx"],
                heading["start_col_offset_idx"],
                heading["col_span"],
            ),
            (0, 1, 2),
        )
        self.assertTrue(
            any(
                c["text"] == "2005–06" and c["start_row_offset_idx"] == 1 for c in cells
            )
        )
        self.assertEqual(self.item["data"]["table_cells"][1]["text"], "Actual 2005-06")

    def test_no_rule_wrong_digit_and_occupied_header_are_unchanged(self):
        no_rules = self.page.filter(lambda obj: obj.get("object_type") != "line")
        self.assertEqual(repair(self.item, no_rules), self.item)
        wrong = copy.deepcopy(self.item)
        wrong["data"]["table_cells"][1]["text"] = "Actual 2005-07"
        self.assertEqual(repair(wrong, self.page), wrong)
        occupied = copy.deepcopy(self.item)
        cell = copy.deepcopy(occupied["data"]["table_cells"][2])
        cell.update(text="Other", start_row_offset_idx=0, end_row_offset_idx=1)
        occupied["data"]["table_cells"].append(cell)
        self.assertEqual(repair(occupied, self.page), occupied)


if __name__ == "__main__":
    unittest.main(verbosity=2)
