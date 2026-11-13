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
from convert import ruled_tables, write_workbook
from layout_partition import recover_partition
from layout_tables import prefer_native


def fixture():
    stream = io.BytesIO()
    p = Canvas(stream, pagesize=(500, 250))
    p.setFont("Helvetica", 10)
    xs = [20, 100, 210, 270, 330, 480]
    ys = [30, 60, 100, 140]
    for x in xs:
        p.line(x, 250 - ys[0], x, 250 - ys[-1])
    for y in ys:
        p.line(100 if y == 100 else 20, 250 - y, 480, 250 - y)
    data = [
        ["Region", "Issue", "Cases", "Deaths", "Comment"],
        ["North", "i. Fever", "46", "0", "No other findings"],
        ["", "ii. Disease", "34", "0", "Follow-up complete"],
    ]
    for r, row in enumerate(data):
        for c, text in enumerate(row):
            if text:
                p.drawString(xs[c] + 4, 250 - ys[r] - 17, text)
    p.save()
    with pdfplumber.open(stream) as pdf:
        native = ruled_tables(pdf.pages[0])[0]
    model = copy.deepcopy(native)
    model["method"] = "layout"
    model.pop("closedGrid")
    by = {(c["r"], c["c"]): c for c in model["cells"]}
    by[1, 0].update(text="North i.", rs=1)
    by[1, 1]["text"] = "Fever 46"
    by[1, 2]["text"] = "0"
    by[1, 3]["text"] = ""
    model["cells"].append(dict(r=2, c=0, rs=1, cs=1, text="ii. Disease"))
    by[2, 1]["text"] = "34"
    by[2, 2]["text"] = "0"
    by[2, 3]["text"] = ""
    return model, native


class PartitionTests(unittest.TestCase):
    def test_complete_source_grid_restores_displaced_words_numbers_and_span(self):
        model, physical = fixture()
        before = copy.deepcopy(model)
        got = prefer_native(model, [physical])
        self.assertIs(got, physical)
        self.assertEqual(model, before)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "table.xlsx"
            write_workbook([dict(got, page=1, index=1)], target, "tables")
            book = load_workbook(target)
            sheet = book.active
            self.assertEqual(sheet["A2"].value, "North")
            self.assertEqual(sheet["B2"].value, "i. Fever")
            self.assertEqual(sheet["C2"].value, "46")
            self.assertEqual(sheet["D2"].value, "0")
            self.assertEqual(sheet["C3"].value, "34")
            self.assertEqual(set(map(str, sheet.merged_cells.ranges)), {"A2:A3"})
            book.close()

    def test_equal_character_bags_do_not_authorize_changed_numbers_or_words(self):
        for old, new in [("46", "64"), ("No other findings", "On other findings")]:
            model, physical = fixture()
            next(c for c in physical["cells"] if c["text"] == old)["text"] = new
            self.assertIs(recover_partition(model, [physical]), model)

    def test_incomplete_overlapping_and_out_of_bounds_grids_abstain(self):
        for change in ["missing", "overlap", "bounds", "open", "dimension", "invalid"]:
            model, physical = fixture()
            if change == "missing":
                physical["cells"].pop()
            elif change == "overlap":
                physical["cells"].append(dict(r=0, c=0, rs=1, cs=1, text=""))
            elif change == "bounds":
                physical["cells"][0]["rs"] = 10**12
            elif change == "open":
                physical["closedGrid"] = False
            elif change == "dimension":
                physical["widths"].append(1)
            else:
                physical["cells"][0]["rs"] = float("nan")
            with self.subTest(change=change):
                self.assertIs(recover_partition(model, [physical]), model)

    def test_ambiguous_or_unrelated_geometry_never_reassigns(self):
        model, physical = fixture()
        self.assertIs(
            recover_partition(model, [physical, copy.deepcopy(physical)]), model
        )
        for change in ["shift", "height", "nonfinite", "negative"]:
            m, p = fixture()
            if change == "shift":
                p["bbox"] = [x + 100 for x in p["bbox"]]
            elif change == "height":
                p["heights"][0] += 10
            elif change == "nonfinite":
                p["bbox"][0] = float("nan")
            else:
                p["widths"][0] = -20
            with self.subTest(change=change):
                self.assertIs(recover_partition(m, [p]), m)

    def test_whole_token_multiplicity_and_punctuation_are_preserved(self):
        for old, new in [
            ("46", "046"),
            ("34", "3.4"),
            ("0", ""),
            ("i. Fever", "i Fever"),
        ]:
            model, physical = fixture()
            next(c for c in physical["cells"] if c["text"] == old)["text"] = new
            self.assertIs(recover_partition(model, [physical]), model)

    def test_words_cannot_move_between_records_even_if_full_table_bag_matches(self):
        model, physical = fixture()
        first = next(c for c in physical["cells"] if c["text"] == "46")
        second = next(c for c in physical["cells"] if c["text"] == "34")
        first["text"], second["text"] = second["text"], first["text"]
        self.assertIs(recover_partition(model, [physical]), model)

    def test_existing_header_columns_and_group_spans_are_not_flattened(self):
        model, physical = fixture()
        first = next(c for c in physical["cells"] if c["text"] == "Region")
        second = next(c for c in physical["cells"] if c["text"] == "Issue")
        first["text"], second["text"] = second["text"], first["text"]
        self.assertIs(recover_partition(model, [physical]), model)
        model, physical = fixture()
        first = next(c for c in physical["cells"] if c["text"] == "Region")
        second = next(c for c in physical["cells"] if c["text"] == "Issue")
        first.update(text="Region Issue", cs=2)
        physical["cells"].remove(second)
        self.assertIs(recover_partition(model, [physical]), model)
