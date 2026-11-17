import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_tables import restore_native_spans


class NativeSpanProofTests(unittest.TestCase):
    def fixture(self):
        base = dict(widths=[60, 60], heights=[20] * 4, bbox=[0, 0, 120, 80])
        header = [
            dict(r=0, c=0, rs=1, cs=1, text="Region"),
            dict(r=0, c=1, rs=1, cs=1, text="Amount"),
        ]
        numbers = [dict(r=r, c=1, rs=1, cs=1, text=f"{r:03d}") for r in range(1, 4)]
        model = dict(
            base,
            cells=header
            + numbers
            + [
                dict(r=1, c=0, rs=2, cs=1, text="Group"),
                dict(r=3, c=0, rs=1, cs=1, text=""),
            ],
        )
        physical = dict(
            base,
            closedGrid=True,
            cells=copy.deepcopy(header + numbers)
            + [dict(r=1, c=0, rs=3, cs=1, text="Group")],
        )
        return model, physical

    def test_single_label_can_expand_into_proven_empty_rows(self):
        model, physical = self.fixture()
        before = copy.deepcopy(model)
        result = restore_native_spans(model, physical)
        self.assertIn(physical["cells"][-1], result["cells"])
        self.assertEqual(
            [c["text"] for c in result["cells"] if c["c"] == 1],
            ["Amount", "001", "002", "003"],
        )
        self.assertEqual(model, before)
        self.assertEqual(restore_native_spans(result, physical), result)

    def test_extension_needs_complete_nonoverlapping_grid_and_unchanged_numeric_anchors(
        self,
    ):
        for mode in [
            "missing",
            "overlap",
            "numeric",
            "other-label",
            "dimensions",
            "bounds",
        ]:
            with self.subTest(mode=mode):
                model, physical = self.fixture()
                if mode == "missing":
                    physical["cells"].pop(3)
                if mode == "overlap":
                    physical["cells"].append(copy.deepcopy(physical["cells"][2]))
                if mode == "numeric":
                    physical["cells"][3]["text"] = "099"
                if mode == "other-label":
                    model["cells"][-1]["text"] = "Other"
                if mode == "dimensions":
                    physical.pop("heights")
                if mode == "bounds":
                    physical["cells"][2]["rs"] = 10**12
                self.assertIs(restore_native_spans(model, physical), model)

    def test_cjk_wrapped_stub_joins_only_inside_verified_physical_span(self):
        model, physical = self.fixture()
        model["cells"][-2:] = [
            dict(r=1, c=0, rs=1, cs=1, text="一级"),
            dict(r=2, c=0, rs=1, cs=1, text="公路"),
            dict(r=3, c=0, rs=1, cs=1, text="二级公路"),
        ]
        physical["cells"][-1:] = [
            dict(r=1, c=0, rs=2, cs=1, text="一级\n公路"),
            dict(r=3, c=0, rs=1, cs=1, text="二级公路"),
        ]
        result = restore_native_spans(model, physical)
        self.assertIn(physical["cells"][-2], result["cells"])
        self.assertNotIn(model["cells"][-2], result["cells"])
        bad = copy.deepcopy(physical)
        bad["cells"].pop(3)
        self.assertIs(restore_native_spans(model, bad), model)

    def test_correct_span_keeps_original_text_and_typography_evidence(self):
        model, physical = self.fixture()
        model["cells"][-2:] = [
            dict(
                r=1,
                c=0,
                rs=3,
                cs=1,
                text="Existing label",
                sourceTextCandidate=[10, 20, 50, 30],
                fontSize=9,
            )
        ]
        physical["cells"][-1]["text"] = "Existing\nlabel"
        self.assertIs(restore_native_spans(model, physical), model)
