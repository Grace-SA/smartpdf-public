from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

import pdfplumber
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_header_unit import recover
from convert import table_from_pdf
from source_context import page_context


class HeaderUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "source.pdf"
        self.values = [
            ["Indicator", "Weight of rate in 2024"],
            ["First", "40"],
            ["Second", "30"],
            ["Third", "20"],
            ["Fourth", "10"],
        ]
        self.draw()
        self.model = dict(
            widths=[190, 130],
            heights=[32, 20, 20, 20, 20],
            bbox=[40, 88, 360, 200],
            method="layout",
            cells=[
                dict(r=r, c=c, rs=1, cs=1, text=v)
                for r, row in enumerate(self.values)
                for c, v in enumerate(row)
            ],
        )
        self.model["cells"][1]["text"] = "(%) rate in 2024"

    def draw(self, *, separator=True, unit="(%)", outside=True):
        canvas = Canvas(str(self.path), pagesize=(400, 400))
        canvas.setFont("Helvetica", 8)
        for y in range(200, 301, 20):
            canvas.line(40, y, 360, y)
        if separator:
            canvas.line(230, 200, 230, 300)
        for r, row in enumerate(self.values):
            for c, value in enumerate(row):
                canvas.drawString(45 if c == 0 else 235, 285 - r * 20, value)
        if outside:
            canvas.drawString(340, 305, unit)
        canvas.save()

    def apply(self, model=None):
        with pdfplumber.open(self.path) as doc:
            return recover(
                self.model if model is None else model, doc.pages[0], table_from_pdf
            )

    def test_recovers_header_and_retains_unit_in_page_context(self):
        before = deepcopy(self.model)
        result = self.apply()
        self.assertIsNot(result, self.model)
        self.assertEqual(result["cells"][1]["text"], self.values[0][1])
        self.assertEqual(self.model, before)
        with pdfplumber.open(self.path) as doc:
            self.assertIn("(%)", page_context(doc.pages[0], [result]))

    def test_all_body_cells_and_numbers_must_agree(self):
        for index, value in [(2, "Changed"), (3, "41"), (4, "First")]:
            model = deepcopy(self.model)
            model["cells"][index]["text"] = value
            self.assertIs(self.apply(model), model)

    def test_missing_separator_or_outside_unit_prevents_rewrite(self):
        self.draw(separator=False)
        self.assertIs(self.apply(), self.model)
        self.draw(outside=False)
        self.assertIs(self.apply(), self.model)
        self.draw(unit="USD")
        self.assertIs(self.apply(), self.model)

    def test_header_suffix_and_digits_cannot_change(self):
        for value in ["(%) rate in 2025", "(%) in rate 2024", "(%) unrelated text"]:
            model = deepcopy(self.model)
            model["cells"][1]["text"] = value
            self.assertIs(self.apply(model), model)

    def test_merged_or_duplicate_model_cells_are_not_rewritten(self):
        model = deepcopy(self.model)
        model["cells"][2]["rs"] = 2
        self.assertIs(self.apply(model), model)
        model = deepcopy(self.model)
        model["cells"].append(deepcopy(model["cells"][2]))
        self.assertIs(self.apply(model), model)

    def test_two_changed_headers_are_not_rewritten(self):
        self.model["cells"][0]["text"] = "Unrelated"
        self.assertIs(self.apply(), self.model)


if __name__ == "__main__":
    unittest.main()
