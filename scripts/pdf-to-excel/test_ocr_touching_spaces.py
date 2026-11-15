import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from ocr_touching_spaces import recover_touching_spaces


class TouchingSpaceTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((50, 140, 3), 255, np.uint8)
        for a, b in [(5, 24), (27, 34), (65, 84), (87, 94)]:
            self.image[15:35, a:b] = 0
        self.box = [[0, 10], [100, 10], [100, 40], [0, 40]]
        self.rows = [[self.box, "AbcDef", 0.99]]
        self.pred = [("Abc Def", 0.99)] * 2 + [("Abc", 0.99)] * 2 + [("Def", 0.99)] * 2

    def test_pixels_full_line_and_all_word_blocks_must_agree(self):
        reader = SimpleNamespace(text_rec=lambda crops: (self.pred, 0))
        output = recover_touching_spaces(self.image, self.rows, reader)
        self.assertEqual(output[0][1], "Abc Def")
        self.assertEqual(self.rows[0][1], "AbcDef")
        self.assertEqual(output[0][0], self.box)

    def test_no_consensus_no_rewrite(self):
        for pred in (
            [],
            None,
            self.pred[:-1],
            self.pred + self.pred,
            [("Abx Def", 0.99)] * 2 + self.pred[2:],
            self.pred[:-1] + [("Dcf", 0.99)],
            self.pred[:-1] + [("Def", 0.94)],
            self.pred[:-1] + [("Def", float("nan"))],
            self.pred[:-1] + [("Def", 1.01)],
            self.pred[:-1] + [("Def", None)],
            self.pred[:-1] + [("Def",)],
            self.pred[:-1] + [("Def!", 0.99)],
        ):
            with self.subTest(pred=pred):
                reader = SimpleNamespace(text_rec=lambda crops, value=pred: (value, 0))
                self.assertEqual(
                    recover_touching_spaces(self.image, self.rows, reader), self.rows
                )

    def test_numbers_symbols_existing_words_and_low_input_are_unchanged(self):
        reader = SimpleNamespace(text_rec=lambda _: self.fail("unsupported input"))
        for text, score in (
            ("Abc123", 0.99),
            ("AbcDef*", 0.99),
            ("Abc Def", 0.99),
            ("AbcDef", 0.94),
        ):
            rows = [[self.box, text, score]]
            self.assertEqual(recover_touching_spaces(self.image, rows, reader), rows)

    def test_no_large_pixel_gap_no_ocr(self):
        image = self.image.copy()
        image[15:35, 34:65] = 0
        reader = SimpleNamespace(text_rec=lambda _: self.fail("no pixel evidence"))
        self.assertEqual(recover_touching_spaces(image, self.rows, reader), self.rows)

    def test_zero_width_box_does_not_break_existing_pipeline(self):
        from ocr_spaces import recover_spaces

        rows = [[[[20, 10], [20, 10], [20, 40], [20, 40]], "AbcDef", 0.99]]
        reader = SimpleNamespace(text_rec=lambda _: self.fail("empty crop"))
        self.assertEqual(recover_spaces(self.image, rows, reader), rows)

    def test_recognition_budget_and_crop_boundaries(self):
        calls = []

        def recognize(crops):
            calls.append(crops)
            self.assertEqual(len(crops), 6)
            self.assertTrue(all(crop.size for crop in crops))
            return self.pred, 0

        rows = self.rows * 12
        out = recover_touching_spaces(
            self.image, rows, SimpleNamespace(text_rec=recognize)
        )
        self.assertEqual(len(calls), 8)
        self.assertEqual([r[1] for r in out], ["Abc Def"] * 8 + ["AbcDef"] * 4)


if __name__ == "__main__":
    unittest.main()
