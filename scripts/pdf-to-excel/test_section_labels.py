import copy
import io
import sys
import tempfile
import unittest
from pathlib import Path

import pdfplumber
from openpyxl import load_workbook
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_section_labels import recover
from layout_tables import adapt_table
from convert import write_workbook


def fixture(indent=45, repeated=True):
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(400, 250))
    pdf.setFont("Helvetica", 10)
    labels = [
        ("Group", 20, 25),
        ("All enrolled", 20, 55),
        ("Track A", indent, 67),
        ("Course One", 70, 85),
        ("Course Two", 70, 100),
        ("Track B", 45, 120),
        ("Course One" if repeated else "Different course", 70, 138),
        ("Course Two", 70, 153),
    ]
    for text, x, y in labels:
        pdf.drawString(x, 250 - y, text)
    for text, x in [("Count", 230), ("Rate", 300)]:
        pdf.drawString(x, 225, text)
    for y in [85, 100, 138, 153]:
        pdf.drawString(230, 250 - y, "12")
        pdf.drawString(300, 250 - y, "50%")
    pdf.save()
    stream.seek(0)
    document = pdfplumber.open(stream)
    page = document.pages[0]
    cells = []

    def cell(r, c, text, x, y, end=None, section=False):
        cells.append(
            dict(
                start_row_offset_idx=r,
                end_row_offset_idx=r + 1,
                start_col_offset_idx=c,
                end_col_offset_idx=c + 1,
                row_span=1,
                col_span=1,
                text=text,
                column_header=r == 0,
                row_header=c == 0 and r not in [0, 1, 4],
                row_section=section,
                bbox=dict(
                    l=x,
                    t=y - 9,
                    r=x + 120 if c == 0 else x + 35,
                    b=(end or y) + 3,
                    coord_origin="TOPLEFT",
                ),
            )
        )

    cell(0, 0, "Group", 20, 25)
    cell(0, 1, "Count", 230, 25)
    cell(0, 2, "Rate", 300, 25)
    cell(1, 0, "All enrolled Track A", 20, 55, 67, True)
    cell(4, 0, "Track B", 45, 120, section=True)
    for r, (text, x, y) in zip([2, 3, 5, 6], [labels[i] for i in [3, 4, 6, 7]]):
        cell(r, 0, text, x, y)
        cell(r, 1, "12", 230, y)
        cell(r, 2, "50%", 300, y)
    item = dict(
        data=dict(num_rows=7, num_cols=3, table_cells=cells),
        prov=[
            dict(bbox=dict(l=15, t=12, r=345, b=165, coord_origin="TOPLEFT"), page_no=1)
        ],
    )
    return document, page, item


class SectionLabelTests(unittest.TestCase):
    def test_source_hierarchy_splits_parent_and_child_without_changing_data(self):
        doc, page, item = fixture()
        with doc:
            original = copy.deepcopy(item)
            got = recover(item, page)
            self.assertEqual(item, original)
            self.assertEqual(got["data"]["num_rows"], 8)
            table = adapt_table(got, page)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "result.xlsx"
            write_workbook([dict(table, page=1, index=1)], target, "tables")
            book = load_workbook(target)
            sheet = book.active
            self.assertEqual(
                [sheet.cell(r, 1).value for r in range(1, 9)],
                [
                    "Group",
                    "All enrolled",
                    "Track A",
                    "Course One",
                    "Course Two",
                    "Track B",
                    "Course One",
                    "Course Two",
                ],
            )
            self.assertEqual([sheet.cell(r, 2).value for r in [4, 5, 7, 8]], ["12"] * 4)
            book.close()

    def test_wrapped_heading_and_unrelated_children_are_not_split(self):
        for kwargs in [dict(indent=20), dict(repeated=False)]:
            doc, page, item = fixture(**kwargs)
            with doc:
                self.assertIs(recover(item, page), item)

    def test_source_words_must_match_complete_model_heading(self):
        doc, page, item = fixture()
        with doc:
            item["data"]["table_cells"][3]["text"] = "All enrolled Track B"
            self.assertIs(recover(item, page), item)

    def test_neighboring_data_and_crossing_spans_prevent_inserting_a_record(self):
        for kind in ["neighbor", "span"]:
            doc, page, item = fixture()
            with doc:
                cell = copy.deepcopy(item["data"]["table_cells"][1])
                if kind == "neighbor":
                    cell.update(
                        start_row_offset_idx=1,
                        end_row_offset_idx=2,
                        column_header=False,
                    )
                else:
                    cell.update(
                        start_row_offset_idx=0, end_row_offset_idx=3, row_span=3
                    )
                item["data"]["table_cells"].append(cell)
                self.assertIs(recover(item, page), item)

    def test_sibling_level_and_explicit_section_evidence_are_required(self):
        for kind in ["indent", "section"]:
            doc, page, item = fixture()
            with doc:
                sibling = next(
                    c for c in item["data"]["table_cells"] if c["text"] == "Track B"
                )
                if kind == "indent":
                    sibling["bbox"]["l"] = 20
                else:
                    sibling["row_section"] = False
                self.assertIs(recover(item, page), item)
