import copy
from pathlib import Path
import sys
import tempfile
import unittest

import pdfplumber
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_tables import axis_aligned_edge, physical_page, prefer_native
from layout_empty_rows import recover


class GridRoundoffTests(unittest.TestCase):
    def test_horizontal_roundoff_is_corrected_without_mutating_source(self):
        edge = dict(
            object_type="line",
            x0=20,
            x1=200,
            top=100,
            bottom=100 + 1e-12,
            orientation="v",
        )
        before = copy.deepcopy(edge)
        fixed = axis_aligned_edge(edge)
        self.assertEqual(fixed["orientation"], "h")
        self.assertEqual(fixed["top"], fixed["bottom"])
        self.assertEqual(edge, before)

    def test_real_slopes_curves_and_nonfinite_edges_are_not_rewritten(self):
        base = dict(
            object_type="line", x0=20, x1=200, top=100, bottom=100.01, orientation="v"
        )
        for changes in [
            {},
            {"bottom": 101},
            {"object_type": "curve", "bottom": 100},
            {"x0": float("nan")},
            {"x1": 21, "bottom": 100},
        ]:
            edge = dict(base, **changes)
            self.assertIs(axis_aligned_edge(edge), edge)

    def test_tiny_vertical_roundoff_is_not_a_horizontal_separator(self):
        edge = dict(
            object_type="line",
            x0=20,
            x1=20 + 1e-12,
            top=100,
            bottom=150,
            orientation=None,
        )
        fixed = axis_aligned_edge(edge)
        self.assertEqual(fixed["orientation"], "v")
        self.assertEqual(fixed["x0"], fixed["x1"])

    def test_physical_grid_recovers_after_transformed_line_roundoff(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid.pdf"
            pdf = Canvas(str(path), pagesize=(300, 300))
            for x in (30, 100, 170, 240):
                pdf.line(x, 100, x, 160)
            for y in (100, 130, 160):
                pdf.line(30, y, 240, y)
            pdf.drawString(40, 140, "Header")
            pdf.save()
            with pdfplumber.open(path) as doc:
                page = doc.pages[0]
                for line in page.lines:
                    if line["x1"] - line["x0"] > 3:
                        line["y1"] += 1e-12
                        line["bottom"] += 1e-12
                self.assertEqual(page.find_tables(), [])
                grids = physical_page(page).find_tables()
                self.assertEqual(len(grids), 1)
                self.assertEqual((len(grids[0].rows), len(grids[0].columns)), (2, 3))

    def tables(self):
        def table(headers, merged):
            cols = len(headers)
            return dict(
                widths=[300 / cols] * cols,
                heights=[20, 20],
                bbox=[0, 0, 300, 40],
                closedGrid=True,
                cells=[
                    dict(r=0, c=i, rs=1, cs=1, text=t) for i, t in enumerate(headers)
                ]
                + [
                    dict(
                        r=1,
                        c=0,
                        rs=1,
                        cs=cols if merged else 1,
                        text="Nothing available",
                    )
                ],
            )

        return table(["Item", "Recorded date Status", "Owner"], False), table(
            ["Item", "Recorded date", "Status", "Owner"], True
        )

    def test_header_separator_and_full_width_body_come_from_unique_grid(self):
        model, native = self.tables()
        before = copy.deepcopy(model)
        self.assertIs(prefer_native(model, [native]), native)
        self.assertEqual(model, before)
        self.assertIs(recover(model, [native, copy.deepcopy(native)]), model)

    def test_small_model_boundary_padding_keeps_unique_physical_grid(self):
        model, native = self.tables()
        model["bbox"] = [-2, -1, 302, 41]
        self.assertIs(recover(model, [native]), native)
        model["bbox"] = [-4, 0, 300, 40]
        self.assertIs(recover(model, [native]), model)

    def test_incomplete_grid_changed_words_order_or_data_are_rejected(self):
        model, native = self.tables()
        for mutate in [
            lambda t: t.update(closedGrid=False),
            lambda t: t["cells"][-1].update(cs=1),
            lambda t: t["cells"][1].update(text="date Recorded"),
            lambda t: t["cells"][1].update(text="Recorded data"),
            lambda t: t["cells"][-1].update(text="Total 12"),
            lambda t: t["cells"].append(dict(r=1, c=1, rs=1, cs=1, text="extra")),
            lambda t: t.update(bbox=[20, 0, 320, 40]),
        ]:
            changed = copy.deepcopy(native)
            mutate(changed)
            self.assertIs(recover(model, [changed]), model)
        model["cells"][-1]["text"] = native["cells"][-1]["text"] = "Total 12"
        self.assertIs(recover(model, [native]), model)


if __name__ == "__main__":
    unittest.main()
