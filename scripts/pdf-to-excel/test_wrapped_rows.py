import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from layout_wrapped_rows import recover


def table(values, heights=None):
    nr, nc = len(values), len(values[0])
    return dict(
        widths=[50] * nc,
        heights=heights or [60 / nr] * nr,
        bbox=[0, 0, 50 * nc, 60],
        closedGrid=True,
        cells=[
            dict(r=r, c=c, rs=1, cs=1, text=v)
            for r, row in enumerate(values)
            for c, v in enumerate(row)
        ],
    )


class WrappedRowsTests(unittest.TestCase):
    def setUp(self):
        self.model = table(
            [
                ["Category", "2024", "2025"],
                ["Coffee,", "12", "21"],
                ["Tea and herbs", "", ""],
            ]
        )
        self.native = table(
            [["Category", "2024", "2025"], ["Coffee, Tea and herbs", "12", "21"]]
        )

    def test_physical_row_retains_words_and_numeric_columns(self):
        original = copy.deepcopy(self.model)
        self.assertIs(recover(self.model, [self.native]), self.native)
        self.assertEqual(self.model, original)

    def test_model_omitted_blank_slots_are_not_missing_source_cells(self):
        self.model["cells"] = [c for c in self.model["cells"] if c["text"]]
        self.assertIs(recover(self.model, [self.native]), self.native)

    def test_partial_or_ambiguous_grid_is_not_used(self):
        for mutate in [
            lambda t: t.update(closedGrid=False),
            lambda t: t["cells"].pop(),
            lambda t: t.update(bbox=[0, 0, 150, 30]),
            lambda t: t["widths"].__setitem__(0, float("nan")),
            lambda t: t["cells"][0].update(cs=2),
        ]:
            candidate = copy.deepcopy(self.native)
            mutate(candidate)
            self.assertIs(recover(self.model, [candidate]), self.model)
        self.assertIs(
            recover(self.model, [self.native, copy.deepcopy(self.native)]), self.model
        )

    def test_no_word_reordering_or_numeric_reassignment(self):
        for value in [
            "Coffee, herbs and Tea",
            "Coffee, Tea and herb",
            "Coffee, Tea and herbs extra",
        ]:
            candidate = copy.deepcopy(self.native)
            candidate["cells"][3]["text"] = value
            self.assertIs(recover(self.model, [candidate]), self.model)
        candidate = copy.deepcopy(self.native)
        candidate["cells"][4]["text"], candidate["cells"][5]["text"] = "21", "12"
        self.assertIs(recover(self.model, [candidate]), self.model)

    def test_numeric_or_multiple_column_continuation_is_not_collapsed(self):
        for continuation in [["Tea 2", "", ""], ["Tea", "extra", ""], ["", "", ""]]:
            model = table([["A", "B", "C"], ["Coffee", "12", "21"], continuation])
            candidate = table(
                [
                    ["A", "B", "C"],
                    [
                        " ".join(filter(None, ["Coffee", continuation[0]])),
                        " ".join(filter(None, ["12", continuation[1]])),
                        "21",
                    ],
                ]
            )
            self.assertIs(recover(model, [candidate]), model)

    def test_header_is_not_merged_or_rewritten(self):
        candidate = copy.deepcopy(self.native)
        candidate["cells"][0]["text"] = "Other category"
        self.assertIs(recover(self.model, [candidate]), self.model)

    def test_two_continuation_lines_and_later_rows(self):
        model = table(
            [
                ["A", "B"],
                ["First", "12"],
                ["middle", ""],
                ["last", ""],
                ["Second", "34"],
            ]
        )
        candidate = table([["A", "B"], ["First middle last", "12"], ["Second", "34"]])
        self.assertIs(recover(model, [candidate]), candidate)


if __name__ == "__main__":
    unittest.main()
