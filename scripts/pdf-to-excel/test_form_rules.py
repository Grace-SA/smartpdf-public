import tempfile, unittest, hashlib, math
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from openpyxl import Workbook
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from xlsx_form_rules import attach


class RuleTests(unittest.TestCase):
    def fixture(self, path):
        b = Workbook()
        s = b.active
        s["A1"] = "Literal =1+1"
        s["B1"] = "☒"
        b.save(path)
        return [
            dict(
                widths=[1.5] * 100,
                sourceRowEdges=[0, 12, 24],
                sourceRules=[dict(x0=3, x1=90, y=15, weight=0.5)],
            )
        ]

    def test_native_line_has_valid_anchors_and_internal_relationship(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.xlsx"
            tables = self.fixture(p)
            sentinel = p.with_name(p.name + ".rules.tmp")
            sentinel.write_text("unrelated")
            with ZipFile(p) as z:
                before = z.read("xl/worksheets/sheet1.xml")
            attach(p, tables)
            self.assertEqual(sentinel.read_text(), "unrelated")
            with ZipFile(p) as z:
                drawing = ET.fromstring(z.read("xl/drawings/form-rules-1.xml"))
                self.assertFalse(any(e.tag.endswith("txBax") for e in drawing.iter()))
                self.assertEqual(
                    len([e for e in drawing.iter() if e.tag.endswith("}sp")]), 1
                )
                marker = next(e for e in drawing.iter() if e.tag.endswith("}from"))
                values = {e.tag.split("}")[-1]: int(e.text) for e in marker}
                self.assertEqual(values, dict(col=2, colOff=0, row=1, rowOff=38100))
                end = next(e for e in drawing.iter() if e.tag.endswith("}to"))
                self.assertEqual(
                    {e.tag.split("}")[-1]: int(e.text) for e in end},
                    dict(col=60, colOff=0, row=1, rowOff=38100),
                )
                relationships = ET.fromstring(
                    z.read("xl/worksheets/_rels/sheet1.xml.rels")
                )
                self.assertTrue(
                    all(
                        e.get("TargetMode") != "External"
                        and not e.get("Target", "").startswith(("http:", "https:"))
                        for e in relationships
                    )
                )
                after = z.read("xl/worksheets/sheet1.xml")
                text = lambda raw: [
                    e.text for e in ET.fromstring(raw).iter() if e.tag.endswith("}t")
                ]
                self.assertEqual(text(before), text(after))

    def test_context_and_form_rules_coexist_in_single_sheet_schema_order(self):
        from convert import write_workbook
        from openpyxl import load_workbook

        table = dict(
            widths=[60, 60], heights=[20, 20], page=1, index=1,
            sourceContext="* Data not available",
            cells=[
                dict(r=0, c=0, rs=1, cs=2, text="Summary"),
                dict(r=1, c=0, rs=1, cs=1, text="00123"),
                dict(r=1, c=1, rs=1, cs=1, text="12.50*"),
            ],
        )
        form = dict(
            widths=[1.5] * 100, heights=[20, 20], page=2, index=1,
            coordinateGrid=True, headerRows=0,
            sourceRowEdges=[0, 20, 40],
            sourceRules=[dict(x0=3, x1=90, y=20, weight=0.5)],
            cells=[dict(r=0, c=0, rs=1, cs=10, text="Form")],
        )
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "mixed.xlsx"
            write_workbook([table, form], output, "single")
            with ZipFile(output) as package:
                sheet = ET.fromstring(package.read("xl/worksheets/sheet1.xml"))
                tags = [child.tag.rsplit("}", 1)[-1] for child in sheet]
                self.assertEqual(tags.count("drawing"), 1)
                self.assertEqual(tags.count("legacyDrawing"), 1)
                self.assertLess(tags.index("drawing"), tags.index("legacyDrawing"))
                relationships = ET.fromstring(
                    package.read("xl/worksheets/_rels/sheet1.xml.rels")
                )
                kinds = {r.get("Type", "").rsplit("/", 1)[-1] for r in relationships}
                self.assertTrue({"comments", "vmlDrawing", "drawing"} <= kinds)
                self.assertEqual(
                    len({r.get("Id") for r in relationships}), len(relationships)
                )
                self.assertTrue(all(r.get("TargetMode") != "External" for r in relationships))
                self.assertIn("xl/drawings/form-rules-1.xml", package.namelist())
            book = load_workbook(output)
            try:
                sheet = book.active
                comments = [c.comment for row in sheet for c in row if c.comment]
                self.assertEqual(len(comments), 1)
                self.assertIn("* Data not available", comments[0].text)
                self.assertEqual(sheet["A2"].value, "Summary")
                self.assertEqual(sheet["A3"].value, "00123")
                self.assertTrue(any(r.min_row == 2 for r in sheet.merged_cells.ranges))
            finally:
                book.close()

    def test_out_of_bounds_rules_and_repeated_attachment_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.xlsx"
            tables = self.fixture(p)
            before = p.read_bytes()
            tables[0]["sourceRules"][0]["x1"] = 1000
            with self.assertRaises(ValueError):
                attach(p, tables)
            self.assertEqual(p.read_bytes(), before)
            tables[0]["sourceRules"][0]["x1"] = 90
            attach(p, tables)
            before = p.read_bytes()
            with self.assertRaises(ValueError):
                attach(p, tables)
            self.assertEqual(p.read_bytes(), before)

    def test_nonfinite_rule_does_not_damage_workbook(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.xlsx"
            tables = self.fixture(p)
            before = p.read_bytes()
            tables[0]["sourceRules"][0]["x0"] = float("nan")
            with self.assertRaises((ValueError, OverflowError)):
                attach(p, tables)
            self.assertEqual(p.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
