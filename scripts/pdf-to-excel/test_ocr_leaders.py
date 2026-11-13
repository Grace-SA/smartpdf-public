import copy, unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
import ocr_leaders as m


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((600, 800, 3), 255, dtype=np.uint8)
        self.result = []
        self.native = []

        def add(text, x, y, width=24):
            b = [x, y, x + width, y + 12]
            self.result.append(
                ([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], text, 0.99)
            )
            self.native.append(dict(box=b, text=text))

        for i, x in enumerate([400, 480, 560, 640]):
            add("Header" + str(i), x - 50, 100, 50)
        for row in range(10):
            add("Label" + str(row), 40, 126 + row * 24, 130)
            for i, x in enumerate([400, 480, 560, 640]):
                add(str(100 + row * 4 + i), x - 24, 126 + row * 24)
        self.reader = SimpleNamespace(
            text_rec=lambda _: self.fail("Invalid input must not invoke OCR")
        )

    def run_case(self, result=None, native=None, image=None, scale=3):
        with patch.object(m, "leaders", return_value=200):
            return m.recover(
                self.image if image is None else image,
                self.result if result is None else result,
                self.reader,
                self.native if native is None else native,
                scale,
            )

    def test_nonfinite_score_and_malformed_point_rejected(self):
        for value in [float("nan"), float("inf"), -1, 2, "0.99"]:
            data = copy.deepcopy(self.result)
            points, text, _ = data[4]
            data[4] = (points, text, value)
            self.assertEqual(
                self.run_case(result=data)[1]["reason"], "invalid-ocr-word"
            )
        data = copy.deepcopy(self.result)
        data[4][0][0].append(3)
        self.assertEqual(self.run_case(result=data)[1]["reason"], "invalid-ocr-box")

    def test_outside_box_and_bad_source_rejected(self):
        data = copy.deepcopy(self.result)
        data[4][0][0][0] = -1
        self.assertEqual(self.run_case(result=data)[1]["reason"], "invalid-ocr-word")
        data = copy.deepcopy(self.native)
        data[0]["box"][0] = float("nan")
        self.assertEqual(self.run_case(native=data)[1]["reason"], "invalid-source-word")

    def test_invalid_image_and_scale_rejected(self):
        for image in [
            np.zeros((0, 0, 3), dtype=np.uint8),
            np.zeros((10, 10), dtype=np.uint8),
            self.image.astype(float),
        ]:
            self.assertEqual(self.run_case(image=image)[1]["reason"], "invalid-image")
        for scale in [0, float("nan"), 10, "3"]:
            self.assertEqual(self.run_case(scale=scale)[1]["reason"], "invalid-scale")

    def test_missing_last_complete_row_rejected(self):
        self.assertEqual(
            self.run_case(result=self.result[:-5])[1]["reason"], "uncovered-source-row"
        )

    def test_missing_middle_complete_row_rejected(self):
        self.assertEqual(
            self.run_case(result=self.result[:24] + self.result[29:])[1]["reason"],
            "uncovered-source-row",
        )

    def test_missing_one_numeric_cell_rejected(self):
        self.assertEqual(
            self.run_case(result=self.result[:7] + self.result[8:])[1]["reason"],
            "uncovered-source-cell",
        )

    def test_missing_header_word_rejected(self):
        self.assertEqual(
            self.run_case(native=self.native[1:])[1]["reason"], "header-segmentation"
        )

    def test_ambiguous_votes_and_changed_number_not_accepted(self):
        field = dict(kind="label", box=[20, 20, 180, 40], original="Item")
        reader = SimpleNamespace(
            text_rec=lambda crops: ([("Alpha", 0.99)] * 4 + [("Beta", 0.99)] * 4, 0)
        )
        with patch.object(m, "from_pixels", return_value=(None, {})):
            self.assertTrue(m.recognize_fields(self.image, [field], reader))
            self.assertNotIn("text", field)
            self.assertEqual(field["failure"], "ambiguous-consensus")
            field = dict(kind="number", box=[20, 20, 180, 40], original="100")
            reader.text_rec = lambda crops: ([("101", 0.99)] * len(crops), 0)
            m.recognize_fields(self.image, [field], reader)
            self.assertNotIn("text", field)


class RefinementGuards(unittest.TestCase):
    def test_tied_scaled_votes_do_not_choose_lexically(self):
        image = np.full((60, 240, 3), 255, dtype=np.uint8)
        field = dict(
            kind="label",
            box=[20, 20, 180, 40],
            original="Item",
            failure="no-two-high-confidence-matches",
        )
        reader = SimpleNamespace(
            text_rec=lambda crops: ([("Alpha", 0.99)] * 3 + [("Beta", 0.99)] * 3, 0)
        )
        m.refine_uncertain(image, [field], reader)
        self.assertNotIn("text", field)

    def test_disagreement_cannot_be_overridden_by_refinement(self):
        image = np.full((60, 240, 3), 255, dtype=np.uint8)
        for failure in ["ambiguous-consensus", "numeric-disagreement"]:
            field = dict(
                kind="label", box=[20, 20, 180, 40], original="Item", failure=failure
            )
            reader = SimpleNamespace(
                text_rec=lambda _: self.fail(
                    "Conflicting evidence must remain unresolved"
                )
            )
            m.refine_uncertain(image, [field], reader)
            self.assertNotIn("text", field)

    def test_invalid_recognition_reply_never_becomes_consensus(self):
        image = np.full((60, 240, 3), 255, dtype=np.uint8)
        for reply in [
            None,
            ([], 0),
            ([("Text", float("nan"))] * 8, 0),
            ([("Text", 2)] * 8, 0),
        ]:
            field = dict(kind="label", box=[20, 20, 180, 40], original="Item")
            reader = SimpleNamespace(text_rec=lambda _, reply=reply: reply)
            self.assertFalse(m.recognize_fields(image, [field], reader))
            self.assertNotIn("text", field)


if __name__ == "__main__":
    unittest.main(verbosity=2)
