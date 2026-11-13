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
