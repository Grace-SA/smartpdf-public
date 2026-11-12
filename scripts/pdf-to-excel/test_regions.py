import sys, tempfile, unittest
from pathlib import Path
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_regions import candidates


class RegionTests(unittest.TestCase):
    def fixture(self, path, numeric=True, grid=True, footer=False):
        p = canvas.Canvas(str(path), pagesize=(800, 600))
        p.setFont("Helvetica", 10)
        if grid:
            for x in [20, 540, 780]:
                p.line(x, 60, x, 550)
            for y in [60, 180, 300, 420, 550]:
                p.line(20, y, 780, y)
        for i in range(12):
            for x, text in [
                (25, f"Record {i+1}"),
                (200, "10.25" if numeric else "paragraph"),
                (300, "20.50" if numeric else "ordinary"),
                (420, "30.75" if numeric else "text"),
            ]:
                p.drawString(x, 530 - i * 35, text)
        # A separate chart column has numerical axis labels but no numeric data rows.
        for i in range(12):
            p.drawString(560, 530 - i * 35, str(i * 10))
        if footer:
            p.line(20, 130, 540, 130)
            p.drawString(25, 75, "Contact address and source note")
        p.save()

    def test_physical_table_column_separates_adjacent_chart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mixed.pdf"
            self.fixture(path)
            with pdfplumber.open(path) as doc:
                self.assertEqual(candidates(doc.pages[0]), [(20.0, 50.0, 540.0, 540.0)])

    def test_prose_and_no_physical_column_do_not_trigger_region_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, kwargs in [
                ("prose", dict(numeric=False)),
                ("no-grid", dict(grid=False)),
            ]:
                path = Path(tmp) / f"{name}.pdf"
                self.fixture(path, **kwargs)
                with pdfplumber.open(path) as doc:
                    self.assertEqual(candidates(doc.pages[0]), [])

    def test_region_attempts_respect_budget_and_reject_incomplete_conversion(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from docling.datamodel.base_models import ConversionStatus
        from layout_regions import recover_regions

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bounded.pdf"
            self.fixture(path)
            converter = Mock()
            converter.convert.return_value = SimpleNamespace(
                status=ConversionStatus.PARTIAL_SUCCESS
            )
            with pdfplumber.open(path) as doc:
                boxes = [(20.0, 50.0, 300.0, 540.0), (320.0, 50.0, 600.0, 540.0)]
                with patch("layout_regions.candidates", return_value=boxes):
                    self.assertEqual(
                        recover_regions(path, 0, doc.pages[0], converter, 0), ([], 0)
                    )
                    self.assertEqual(
                        recover_regions(path, 0, doc.pages[0], converter, 1), ([], 1)
                    )
            self.assertEqual(converter.convert.call_count, 1)
            self.assertEqual(converter.convert.call_args.kwargs["max_num_pages"], 1)

    def test_visible_closing_rule_excludes_contact_footer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "footer.pdf"
            self.fixture(path, footer=True)
            with pdfplumber.open(path) as doc:
                self.assertEqual(candidates(doc.pages[0]), [(20.0, 50.0, 540.0, 470.0)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
