import sys, io, copy, unittest, importlib.util
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

G = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(G / "server/pdf-to-excel"))
from layout_tables import local_box
import layout_header_tree as m


def fixture(
    missing_rule=False, blocked_leaf=False, separate_headings=False, group_label="Group"
):
    b = io.BytesIO()
    p = canvas.Canvas(b, pagesize=(420, 400))
    p.setFont("Helvetica", 10)
    for x, y, t in [
        (205, 360, group_label),
        (280, 340, "Control"),
        (30, 320, "Stub"),
        (130, 320, "Total"),
        (250, 320, "Public"),
        (330, 320, "Private"),
    ]:
        p.drawString(x, y, t)
    if separate_headings:
        p.drawString(330, 360, "Other")
    for y in [374, 314]:
        p.line(20, y, 390, y)
    if not missing_rule:
        p.line(120, 354, 390, 354)
    p.line(240, 334, 390, 334)
    if blocked_leaf:
        p.line(120, 334, 170, 334)
    for r in range(4):
        for x, t in [
            (30, f"Row{r}"),
            (130, str(100 + r)),
            (250, str(200 + r)),
            (330, str(300 + r)),
        ]:
            p.drawString(x, 290 - r * 20, t)
    p.save()
    b.seek(0)
    doc = pdfplumber.open(b)
    page = doc.pages[0]
    words = page.extract_words()
    cells = []

    def cell(row, col, text, source, rs=1, cs=1):
        ws = [w for w in words if w["text"] in source]
        box = [
            min(w["x0"] for w in ws),
            min(w["top"] for w in ws),
            max(w["x1"] for w in ws),
            max(w["bottom"] for w in ws),
        ]
        cells.append(
            dict(
                start_row_offset_idx=row,
                end_row_offset_idx=row + rs,
                start_col_offset_idx=col,
                end_col_offset_idx=col + cs,
                row_span=rs,
                col_span=cs,
                text=text,
                bbox=local_box(box, page),
                column_header=row < 3,
            )
        )

    cell(0, 0, "Stub", ["Stub"], rs=3)
    cell(2, 1, "Total", ["Total"])
    cell(
        2,
        2,
        f"{group_label} Other Public" if separate_headings else f"{group_label} Public",
        (
            [group_label, "Other", "Public"]
            if separate_headings
            else [group_label, "Public"]
        ),
    )
    cell(1, 2, "Control", ["Control"], cs=2)
    cell(2, 3, "Private", ["Private"])
    for r in range(4):
        for col, t in enumerate([f"Row{r}", str(100 + r), str(200 + r), str(300 + r)]):
            cell(r + 3, col, t, [t])
    item = dict(
        prov=[dict(bbox=local_box([20, 25, 390, 180], page))],
        data=dict(num_rows=7, num_cols=4, table_cells=cells),
    )
    return doc, page, item


class HeaderTreeTests(unittest.TestCase):
    def test_source_group_and_vertical_spans_recovered_without_body_changes(self):
        doc, p, item = fixture()
        try:
            original = copy.deepcopy(item)
            got = m.recover(item, p)
            self.assertIsNot(got, item)
            self.assertEqual(item, original)
            cells = got["data"]["table_cells"]
            headers = {
                (c["start_row_offset_idx"], c["start_col_offset_idx"]): (
                    c["text"],
                    c["row_span"],
                    c["col_span"],
                )
                for c in cells
                if c["start_row_offset_idx"] < 3
            }
            self.assertEqual(
                headers,
                {
                    (0, 0): ("Stub", 3, 1),
                    (0, 1): ("Group", 1, 3),
                    (1, 1): ("Total", 2, 1),
                    (1, 2): ("Control", 1, 2),
                    (2, 2): ("Public", 1, 1),
                    (2, 3): ("Private", 1, 1),
                },
            )
            self.assertEqual(
                [c for c in cells if c["start_row_offset_idx"] >= 3],
                [
                    c
                    for c in item["data"]["table_cells"]
                    if c["start_row_offset_idx"] >= 3
                ],
            )
        finally:
            doc.close()

    def test_separated_titles_over_one_rule_are_not_joined(self):
        doc, p, item = fixture(separate_headings=True)
        try:
            self.assertIs(m.recover(item, p), item)
        finally:
            doc.close()

    def test_missing_physical_group_rule_keeps_model(self):
        doc, p, item = fixture(missing_rule=True)
        try:
            self.assertIs(m.recover(item, p), item)
        finally:
            doc.close()

    def test_leaf_separator_prevents_vertical_merge(self):
        doc, p, item = fixture(blocked_leaf=True)
        try:
            self.assertIs(m.recover(item, p), item)
        finally:
            doc.close()

    def test_source_character_disagreement_does_not_guess(self):
        doc, p, item = fixture()
        try:
            item["data"]["table_cells"][2]["text"] = "Group Publi"
            self.assertIs(m.recover(item, p), item)
        finally:
            doc.close()

    def test_swapped_column_labels_do_not_pass_global_character_count(self):
        doc, p, item = fixture()
        try:
            a = item["data"]["table_cells"][1]
            b = item["data"]["table_cells"][4]
            a["text"], b["text"] = b["text"], a["text"]
            self.assertIs(m.recover(item, p), item)
        finally:
            doc.close()

    def test_numeric_year_group_is_supported_by_physical_rule(self):
        doc, page, item = fixture(group_label="2024")
        try:
            got = m.recover(item, page)
            self.assertIsNot(got, item)
            group = next(c for c in got["data"]["table_cells"] if c["text"] == "2024")
            self.assertEqual(
                (
                    group["start_row_offset_idx"],
                    group["start_col_offset_idx"],
                    group["col_span"],
                ),
                (0, 1, 3),
            )
        finally:
            doc.close()

    def test_unlabelled_stub_uses_complete_physical_header(self):
        doc, page, item = fixture()
        try:
            item["data"]["table_cells"][0]["column_header"] = False
            got = m.recover(item, page)
            self.assertIsNot(got, item)
            stub = next(c for c in got["data"]["table_cells"] if c["text"] == "Stub")
            self.assertEqual(stub["row_span"], 3)
        finally:
            doc.close()

    def test_clipped_leaf_box_does_not_drop_first_letter(self):
        doc, page, item = fixture()
        try:
            total = next(c for c in item["data"]["table_cells"] if c["text"] == "Total")
            total["bbox"]["l"] += 5
            got = m.recover(item, page)
            self.assertIsNot(got, item)
            leaf = next(
                c
                for c in got["data"]["table_cells"]
                if c["start_col_offset_idx"] == 1 and c["start_row_offset_idx"] == 1
            )
            self.assertEqual((leaf["text"], leaf["row_span"]), ("Total", 2))
        finally:
            doc.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
