import sys, tempfile, unittest, copy
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_sections import restore_section_headers as repair
from layout_tables import local_box


class SectionTests(unittest.TestCase):
    def fixture(self, path, bold=True, rule=True, divider=False):
        p = canvas.Canvas(str(path), pagesize=(320, 600))
        p.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        p.drawString(40, 500, "Group 100")
        if rule:
            p.line(35, 515, 280, 515)
        if divider:
            p.line(150, 480, 150, 520)
        p.setFont("Helvetica", 10)
        for r in range(4):
            for x, text in [(40, f"Record{r}"), (160, "00123"), (240, "10.25")]:
                p.drawString(x, 475 - r * 25, text)
        p.save()

    def item(self, page):
        cell = dict(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            row_span=1,
            col_span=1,
            text="Group 100",
            bbox=local_box([39, 91, 65, 104], page),
        )
        cells = [cell]
        for r in range(2, 6):
            for c, text in enumerate([f"Record{r-2}", "00123", "10.25"]):
                cells.append(
                    dict(
                        start_row_offset_idx=r,
                        end_row_offset_idx=r + 1,
                        start_col_offset_idx=c,
                        end_col_offset_idx=c + 1,
                        row_span=1,
                        col_span=1,
                        text=text,
                    )
                )
        return dict(
            prov=[dict(bbox=local_box([35, 55, 280, 240], page))],
            data=dict(num_rows=6, num_cols=3, table_cells=cells),
        )

    def test_bold_ruled_section_recovers_complete_title_and_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "section.pdf"
            self.fixture(p)
            with pdfplumber.open(p) as doc:
                item = self.item(doc.pages[0])
                out = repair(item, doc.pages[0])
                self.assertEqual(out["data"]["table_cells"][0]["col_span"], 3)
                self.assertEqual(out["data"]["table_cells"][0]["text"], "Group 100")
                self.assertEqual(item["data"]["table_cells"][0]["col_span"], 1)

    def test_visible_separator_nonbold_no_rule_and_changed_number_are_not_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n, kwargs in [
                ("line", dict(divider=True)),
                ("regular", dict(bold=False)),
                ("no-rule", dict(rule=False)),
            ]:
                p = Path(tmp) / f"{n}.pdf"
                self.fixture(p, **kwargs)
                with pdfplumber.open(p) as doc:
                    item = self.item(doc.pages[0])
                    self.assertEqual(repair(item, doc.pages[0]), item)
            p = Path(tmp) / "wrong.pdf"
            self.fixture(p)
            with pdfplumber.open(p) as doc:
                item = self.item(doc.pages[0])
                item["data"]["table_cells"][0]["text"] = "Group 101"
                self.assertEqual(repair(item, doc.pages[0]), item)
                item = self.item(doc.pages[0])
                c = copy.deepcopy(item["data"]["table_cells"][1])
                c.update(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text="0",
                )
                item["data"]["table_cells"].append(c)
                self.assertEqual(repair(item, doc.pages[0]), item)


if __name__ == "__main__":
    unittest.main(verbosity=2)
