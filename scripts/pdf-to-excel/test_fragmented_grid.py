import copy
import io
import sys
import tempfile
import unittest
from pathlib import Path

import pdfplumber
from reportlab.pdfgen.canvas import Canvas
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_fragmented_grid import restore_fragmented_rows
from convert import table_from_pdf, write_workbook


def fixture(extra_ink=False, partial_separator=False, missing_rule=False):
    stream = io.BytesIO()
    pdf = Canvas(stream, pagesize=(360, 320))
    pdf.setFont("Helvetica", 10)
    xs = [20, 140, 220, 300]
    ys = [40 + 30 * r for r in range(8)]
    cells = []
    for y in ys:
        if not (missing_rule and y == 130):
            pdf.line(20, 320 - y, 300, 320 - y)
    for x in xs:
        pdf.line(x, 320 - 40, x, 320 - 130)
        pdf.line(x, 320 - 160, x, 320 - 250)
    if partial_separator:
        pdf.line(140, 320 - 130, 140, 320 - 160)
    for r in range(7):
        values = (
            ["Name", "Count", "Price"]
            if r == 0
            else ["Category", "", ""] if r == 3 else [f"Row{r}", f"{r}1.0", f"{r}2.0"]
        )
        for c, text in enumerate(values):
            if text:
                pdf.drawString(xs[c] + 4, 320 - ys[r] - 17, text)
            cells.append(dict(r=r, c=c, rs=1, cs=1, text=text))
    if extra_ink:
        pdf.drawString(230, 320 - 130 - 17, "99")
    pdf.save()
    doc = pdfplumber.open(stream)
    table = dict(
        bbox=[20, 40, 300, 250],
        widths=[120, 80, 80],
        heights=[30] * 7,
        cells=cells,
        method="layout",
        page=1,
        index=1,
    )
    return doc, table


class FragmentedGridTests(unittest.TestCase):
    def test_complete_numeric_grid_and_open_category_row_restore_one_merge(self):
        doc, table = fixture()
        try:
            original = copy.deepcopy(table)
            got = restore_fragmented_rows(table, doc.pages[0], table_from_pdf)
            self.assertIsNot(got, table)
            self.assertEqual(table, original)
            self.assertEqual(
                [(c["r"], c["c"], c["cs"]) for c in got["cells"] if c["cs"] > 1],
                [(3, 0, 3)],
            )
            self.assertEqual(
                {(c["r"], c["c"]): c["text"] for c in got["cells"] if c["text"]},
                {(c["r"], c["c"]): c["text"] for c in table["cells"] if c["text"]},
            )
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "grid.xlsx"
                write_workbook([got], output, "tables")
                book = load_workbook(output)
                self.assertEqual(
                    list(map(str, book.active.merged_cells.ranges)), ["A4:C4"]
                )
                self.assertEqual(book.active["C7"].value, "62.0")
                book.close()
        finally:
            doc.close()

    def test_extra_ink_partial_separator_and_missing_boundary_abstain(self):
        for options in [
            dict(extra_ink=True),
            dict(partial_separator=True),
            dict(missing_rule=True),
        ]:
            doc, table = fixture(**options)
            try:
                with self.subTest(options=options):
                    self.assertIs(
                        restore_fragmented_rows(table, doc.pages[0], table_from_pdf),
                        table,
                    )
            finally:
                doc.close()

    def test_changed_value_missing_cell_or_crossing_span_abstain(self):
        for change in ["value", "missing", "span"]:
            doc, table = fixture()
            try:
                if change == "value":
                    table["cells"][4]["text"] = "999"
                elif change == "missing":
                    table["cells"][4]["text"] = ""
                else:
                    table["cells"][6]["rs"] = 2
                with self.subTest(change=change):
                    self.assertIs(
                        restore_fragmented_rows(table, doc.pages[0], table_from_pdf),
                        table,
                    )
            finally:
                doc.close()

    def test_already_correct_merge_and_shape_mismatch_keep_existing_table(self):
        for change in ["correct", "columns", "rows", "label"]:
            doc, table = fixture()
            try:
                if change == "correct":
                    table["cells"][9]["cs"] = 3
                    table["cells"] = [
                        c for c in table["cells"] if c["r"] != 3 or c["c"] == 0
                    ]
                elif change == "columns":
                    table["widths"].append(10)
                elif change == "rows":
                    table["heights"].append(10)
                else:
                    table["cells"][9]["text"] = "Different category"
                with self.subTest(change=change):
                    self.assertIs(
                        restore_fragmented_rows(table, doc.pages[0], table_from_pdf),
                        table,
                    )
            finally:
                doc.close()
