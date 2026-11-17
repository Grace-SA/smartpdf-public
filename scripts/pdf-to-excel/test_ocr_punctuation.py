import sys, unittest, copy
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from ocr_punctuation import resolve


class PunctuationTests(unittest.TestCase):
    def field(self):
        return dict(
            kind="label",
            box=[0, 0, 300, 60],
            failure="ambiguous-consensus",
            ambiguousValues=["ABCD - EFGH", "ABCD . EFGH"],
            alternatives=[("ABCD - EFGH", 0.99)] * 2 + [("ABCD . EFGH", 0.98)] * 2,
        )

    def image(self, mark):
        image = np.full((60, 300, 3), 255, dtype=np.uint8)
        for i in range(9):
            x = 10 + i * 30
            if i != 4:
                image[10:40, x : x + 15] = 0
            elif mark == "hyphen":
                image[24:28, x : x + 10] = 0
            elif mark == "period":
                image[35:40, x : x + 5] = 0
            else:
                image[24:29, x : x + 5] = 0
        return image

    def test_baseline_period_and_centered_hyphen_require_distinct_ink(self):
        for mark, expected in [("hyphen", "ABCD - EFGH"), ("period", "ABCD . EFGH")]:
            field = self.field()
            resolve(self.image(mark), [field])
            self.assertEqual(field["text"], expected)
            self.assertEqual(field["refinement"], "isolated-punctuation-geometry")

    def test_centered_dot_and_extra_component_do_not_break_tie(self):
        field = self.field()
        resolve(self.image("middle-dot"), [field])
        self.assertNotIn("text", field)
        image = self.image("hyphen")
        image[1:3, 1:3] = 0
        field = self.field()
        resolve(image, [field])
        self.assertNotIn("text", field)

    def test_numbers_letters_and_unsupported_changes_never_rewritten(self):
        for options in [
            ["1234 - 5678", "1234 . 5678"],
            ["ABCD - EFGH", "ABCD . EFGX"],
            ["ABCD : EFGH", "ABCD . EFGH"],
        ]:
            field = self.field()
            field["ambiguousValues"] = options
            resolve(self.image("hyphen"), [field])
            self.assertNotIn("text", field)

    def test_ink_alone_does_not_replace_missing_recognition_consensus(self):
        field = self.field()
        field["alternatives"] = [("ABCD - EFGH", 0.99), ("ABCD - EFGH", 0.7)]
        resolve(self.image("hyphen"), [field])
        self.assertNotIn("text", field)


if __name__ == "__main__":
    unittest.main(verbosity=2)
