import sys, tempfile, unittest, copy
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_grid import recover_source_grid
from layout_tables import local_box


class GridRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "fixture.pdf"
        p = canvas.Canvas(str(self.path), pagesize=(500, 600))
        p.setFont("Helvetica", 10)
        for y in [280, 315, 350, 385, 420, 500]:
            p.line(100, y, 340, y)
        for x in [100, 180, 260, 340]:
            p.line(x, 280, x, 500)
        self.text = ["Count One", "Quantity Two", "Value Three"]
        for x, label in zip([120, 200, 280], self.text):
            p.saveState()
            p.translate(x, 430)
            p.rotate(90)
            p.drawString(0, 0, label)
            p.restoreState()
        for r, y in enumerate([400, 365, 330, 295]):
            label = f"Record {r+1}"
            p.drawString(40, y, label)
            self.text.append(label)
            for c, x in enumerate([105, 185, 265]):
                v = f"{r*3+c:03}"
                p.drawString(x, y, v)
                self.text.append(v)
        for y in [245, 265]:
            p.line(180, y, 340, y)
        for x in [180, 260, 340]:
            p.line(x, 245, x, 265)
        for x, v in [(40, "Totals"), (105, "006"), (185, "022"), (265, "038")]:
            p.drawString(x, 251, v)
            self.text.append(v)
        p.save()
        self.doc = pdfplumber.open(self.path)
        self.page = self.doc.pages[0]
        self.item = {
            "prov": [{"bbox": local_box([38, 99, 341, 357], self.page)}],
            "data": {"table_cells": [dict(text=t) for t in self.text]},
        }

    def tearDown(self):
        self.doc.close()
        self.tmp.cleanup()

    def test_vertical_headers_stub_and_separate_total(self):
        table = recover_source_grid(self.item, self.page)
        self.assertIsNotNone(table)
        self.assertEqual(len(table["widths"]), 4)
        self.assertEqual(
            [c.get("rotation") for c in table["cells"] if c["text"] in self.text[:3]],
            [90, 90, 90],
        )
        values = {(c["r"], c["c"]): c["text"] for c in table["cells"]}
        self.assertEqual([values[(0, c)] for c in [1, 2, 3]], self.text[:3])
        for r in range(4):
            self.assertEqual(values[(r + 1, 0)], f"Record {r+1}")
            self.assertEqual(
                [values[(r + 1, c + 1)] for c in range(3)],
                [f"{r*3+c:03}" for c in range(3)],
            )
        last = len(table["heights"]) - 1
        self.assertEqual(
            [values[(last, c)] for c in range(4)], ["Totals", "006", "022", "038"]
        )
        self.assertAlmostEqual(
            sum(table["heights"]), table["bbox"][3] - table["bbox"][1]
        )

    def test_changed_number_or_missing_text_is_rejected(self):
        for alter in ["999", ""]:
            item = copy.deepcopy(self.item)
            item["data"]["table_cells"][5]["text"] = alter
            self.assertIsNone(recover_source_grid(item, self.page))

    def test_adapter_recovers_conflicting_model_spans_using_source_grid(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from docling.datamodel.base_models import ConversionStatus
        from layout_tables import extract_layout_tables
        from convert import ruled_tables

        item = copy.deepcopy(self.item)
        item["prov"][0]["page_no"] = 1
        item["data"].update(num_rows=6, num_cols=4)
        for cell in item["data"]["table_cells"]:
            cell.update(
                start_row_offset_idx=0,
                end_row_offset_idx=1,
                start_col_offset_idx=0,
                end_col_offset_idx=1,
                row_span=1,
                col_span=1,
            )
        prediction = SimpleNamespace(
            data=SimpleNamespace(num_rows=6, num_cols=4),
            prov=[SimpleNamespace(page_no=1)],
            model_dump=lambda: item,
        )
        detector = SimpleNamespace(
            convert=lambda *args, **kwargs: SimpleNamespace(
                status=ConversionStatus.SUCCESS,
                document=SimpleNamespace(tables=[prediction]),
            )
        )
        with patch("layout_tables.converter_for", return_value=detector):
            tables = extract_layout_tables(
                self.path, [0], "unused", self.doc.pages, ruled_tables
            )
        self.assertEqual(len(tables[0]), 1)
        self.assertEqual(tables[0][0]["method"], "ruled-recovery")
        self.assertEqual(
            sorted(c["text"] for c in tables[0][0]["cells"] if c["text"]),
            sorted(self.text),
        )

    def test_large_unrelated_region_is_not_assumed_to_be_a_stub(self):
        item = copy.deepcopy(self.item)
        item["prov"][0]["bbox"] = local_box([0, 0, 500, 600], self.page)
        self.assertIsNone(recover_source_grid(item, self.page))

    def test_workbook_preserves_narrow_columns_vertical_text_and_no_header(self):
        from convert import write_workbook
        from openpyxl import load_workbook

        table = dict(
            page=1,
            index=1,
            widths=[26, 130],
            heights=[110, 20],
            sourceGeometry=True,
            headerRows=0,
            fontSize=8,
            cells=[
                dict(r=0, c=0, rs=1, cs=1, text="Vertical label", rotation=90),
                dict(r=0, c=1, rs=1, cs=1, text="00123"),
                dict(r=1, c=0, rs=1, cs=1, text="123"),
                dict(r=1, c=1, rs=1, cs=1, text="456"),
            ],
        )
        output = Path(self.tmp.name) / "geometry.xlsx"
        write_workbook([table], output, "tables")
        book = load_workbook(output)
        self.assertAlmostEqual(book.active.column_dimensions["A"].width, 26 / 5.25)
        self.assertEqual(book.active["A1"].alignment.textRotation, 90)
        self.assertFalse(book.active["A1"].font.bold)
        self.assertEqual(book.active["B1"].value, "00123")
        book.close()

    def test_sparse_grid_keeps_empty_cell_borders_and_merge_perimeter(self):
        from convert import write_workbook
        from openpyxl import load_workbook

        table = dict(
            page=1,
            index=1,
            widths=[80, 80, 80],
            heights=[20, 20, 20],
            cells=[
                dict(r=0, c=0, rs=1, cs=3, text="Heading"),
                dict(r=1, c=0, rs=1, cs=1, text="00123"),
                dict(r=2, c=2, rs=1, cs=1, text="0.00"),
            ],
        )
        output = Path(self.tmp.name) / "sparse.xlsx"
        write_workbook([table], output, "tables")
        book = load_workbook(output)
        sheet = book.active
        self.assertEqual((sheet.max_row, sheet.max_column), (3, 3))
        self.assertIsNone(sheet["C2"].value)
        self.assertEqual(sheet["C2"].border.right.style, "thin")
        self.assertEqual(sheet["C2"].border.bottom.style, "thin")
        self.assertEqual(set(map(str, sheet.merged_cells.ranges)), {"A1:C1"})
        self.assertEqual(sheet["C1"].border.right.style, "thin")
        self.assertIsNone(sheet["B1"].border.right.style)
        self.assertEqual(sheet["A2"].value, "00123")
        self.assertEqual(sheet["C3"].value, "0.00")
        book.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
