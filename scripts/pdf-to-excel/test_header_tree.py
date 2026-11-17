import sys, io, copy, unittest, importlib.util
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

G = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(G / "server/pdf-to-excel"))
from layout_tables import local_box
import layout_header_tree as m


def fixture(
    missing_rule=False,
    blocked_leaf=False,
    separate_headings=False,
    group_label="Group",
    filled_rule=False,
    overhang_stub=False,
):
    b = io.BytesIO()
    p = canvas.Canvas(b, pagesize=(420, 400))
    p.setFont("Helvetica", 10)
    for x, y, t in [
        (205, 360, group_label),
        (280, 340, "Control"),
        (
            30,
            340 if overhang_stub else 320,
            "Extraordinarilylongstubheading" if overhang_stub else "Stub",
        ),
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
        if filled_rule:
            p.rect(120, 354 - 0.96, 270, 0.96, stroke=0, fill=1)
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

    stub = "Extraordinarilylongstubheading" if overhang_stub else "Stub"
    cell(0, 0, stub, [stub], rs=3)
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

    def test_filled_underline_edges_do_not_create_an_extra_header_level(self):
        doc, page, item = fixture(filled_rule=True)
        try:
            got = m.recover(item, page)
            self.assertIsNot(got, item)
            self.assertEqual(got["data"]["num_rows"], 7)
            group = next(c for c in got["data"]["table_cells"] if c["text"] == "Group")
            self.assertEqual((group["start_row_offset_idx"], group["col_span"]), (0, 3))
        finally:
            doc.close()

    def test_physical_levels_remove_only_spurious_header_row(self):
        doc, page, item = fixture(filled_rule=True)
        try:
            original_body = copy.deepcopy(
                [c for c in item["data"]["table_cells"] if not c["column_header"]]
            )
            for c in item["data"]["table_cells"]:
                if c["start_row_offset_idx"]:
                    c["start_row_offset_idx"] += 1
                    c["end_row_offset_idx"] += 1
                else:
                    c["end_row_offset_idx"] += 1
                    c["row_span"] += 1
            item["data"]["num_rows"] += 1
            before = copy.deepcopy(item)
            got = m.recover(item, page)
            self.assertIsNot(got, item)
            self.assertEqual(item, before)
            self.assertEqual(got["data"]["num_rows"], 7)
            self.assertEqual(
                [c for c in got["data"]["table_cells"] if not c["column_header"]],
                original_body,
            )
            self.assertEqual(
                next(c for c in got["data"]["table_cells"] if c["text"] == "Stub")[
                    "row_span"
                ],
                3,
            )
        finally:
            doc.close()

    def test_unique_source_word_box_retains_wide_stub_in_its_column(self):
        doc, page, item = fixture(overhang_stub=True)
        try:
            total = next(c for c in item["data"]["table_cells"] if c["text"] == "Total")
            total["bbox"]["l"] += 5
            got = m.recover(item, page)
            self.assertIsNot(got, item)
            stub = next(
                c
                for c in got["data"]["table_cells"]
                if c["text"] == "Extraordinarilylongstubheading"
            )
            self.assertEqual((stub["start_col_offset_idx"], stub["row_span"]), (0, 3))
        finally:
            doc.close()

    def test_separate_close_rules_are_not_treated_as_a_filled_underline(self):
        from types import SimpleNamespace

        page = SimpleNamespace(
            edges=[
                dict(orientation="h", x0=10, x1=100, top=y, bottom=y) for y in [10, 11]
            ],
            rects=[],
        )
        self.assertEqual([e["top"] for e in m.source_header_edges(page)], [10, 11])

    def test_missing_peer_group_rule_does_not_split_its_caption_into_leaves(self):
        stream = io.BytesIO()
        pdf = canvas.Canvas(stream, pagesize=(420, 400))
        pdf.setFont("Helvetica", 10)
        labels = ["Leaf0", "Leaf1", "Leaf2", "Leaf3"]
        pdf.drawString(60, 360, "Left Group")
        pdf.drawString(280, 360, "Right Group")
        for x, value in zip([30, 130, 250, 330], labels):
            pdf.drawString(x, 320, value)
        for y in [374, 314]:
            pdf.line(20, y, 390, y)
        pdf.line(20, 354, 190, 354)
        for r in range(4):
            for c, x in enumerate([30, 130, 250, 330]):
                pdf.drawString(x, 290 - r * 20, f"{c+1}{r+1}")
        pdf.save()
        with pdfplumber.open(stream) as doc:
            page = doc.pages[0]
            words = page.extract_words()
            cells = []

            def add(row, col, text, cs=1):
                selected = [
                    w
                    for w in words
                    if w["text"] in text.split()
                    and (w["x0"] < 200 if col < 2 else w["x0"] >= 200)
                ]
                bounds = [
                    min(w["x0"] for w in selected),
                    min(w["top"] for w in selected),
                    max(w["x1"] for w in selected),
                    max(w["bottom"] for w in selected),
                ]
                cells.append(
                    dict(
                        start_row_offset_idx=row,
                        end_row_offset_idx=row + 1,
                        start_col_offset_idx=col,
                        end_col_offset_idx=col + cs,
                        row_span=1,
                        col_span=cs,
                        text=text,
                        bbox=local_box(bounds, page),
                        column_header=row < 2,
                    )
                )

            add(0, 0, "Left Group", 2)
            add(0, 2, "Right Group", 2)
            for c, label in enumerate(labels):
                add(1, c, label)
            for r in range(4):
                for c in range(4):
                    add(r + 2, c, f"{c+1}{r+1}")
            item = dict(
                prov=[dict(bbox=local_box([20, 25, 390, 180], page))],
                data=dict(num_rows=6, num_cols=4, table_cells=cells),
            )
            self.assertIs(m.recover(item, page), item)


if __name__ == "__main__":
    unittest.main(verbosity=2)
