import sys, unittest
from types import SimpleNamespace
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from ocr_spaces import recover_spaces


class SpaceTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((80, 130, 3), 255, dtype=np.uint8)
        left = 15
        for width, gap in [(10, 12), (10, 2), (4, 2), (8, 2), (8, 0)]:
            self.image[20:42, left : left + width] = 0
            left += width + gap
        self.result = [[[[12, 17], [80, 17], [80, 45], [12, 45]], "LRibs", 0.99]]

    def test_geometry_and_two_recognition_passes_agree(self):
        reader = SimpleNamespace(
            text_rec=lambda crops: ([("L Ribs", 0.98)] * len(crops), 0)
        )
        out = recover_spaces(self.image, self.result, reader)
        self.assertEqual(out[0][1], "L Ribs")
        self.assertEqual(self.result[0][1], "LRibs")
        self.assertEqual(out[0][0], self.result[0][0])

    def test_changed_letters_low_confidence_disagreement_and_no_gap_stay_unchanged(
        self,
    ):
        for replies in [
            None,
            [("L Ribs",)] * 2,
            [],
            [("L Ribs", 0.99)] * 3,
            [("L Ribs", None)] * 2,
            [("L Ribs", 0.99)],
            [("L Ribs", float("nan"))] * 2,
            [("L Ribs", 1.1)] * 2,
            [("L Ribs", 0.94)] * 2,
            [("L Rib5", 0.99)] * 2,
            [("L Ribs", 0.99), ("LRibs", 0.99)],
        ]:
            with self.subTest(replies=replies):
                reader = SimpleNamespace(text_rec=lambda crops: (replies, 0))
                self.assertEqual(
                    recover_spaces(self.image, self.result, reader), self.result
                )
        image = self.image.copy()
        image[20:42, 25:37] = 0
        reader = SimpleNamespace(
            text_rec=lambda _: self.fail("No geometric candidate should reach OCR")
        )
        self.assertEqual(recover_spaces(image, self.result, reader), self.result)

    def test_crop_boundary_whitespace_does_not_veto_internal_consensus(self):
        reader = SimpleNamespace(
            text_rec=lambda crops: ([(" L Ribs", 0.99), ("L Ribs ", 0.98)], 0)
        )
        out = recover_spaces(self.image, self.result, reader)
        self.assertEqual(out[0][1], "L Ribs")
        self.assertEqual(out[0][2], 0.98)
        self.assertEqual(self.result[0][1], "LRibs")

    def test_existing_spaces_or_numeric_values_are_not_rewritten(self):
        reader = SimpleNamespace(
            text_rec=lambda _: self.fail("Unsupported candidate should not reach OCR")
        )
        for text in ["L Ribs", "00123", "12.34", "AB123", "中文"]:
            result = [[self.result[0][0], text, 0.99]]
            self.assertEqual(recover_spaces(self.image, result, reader), result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
