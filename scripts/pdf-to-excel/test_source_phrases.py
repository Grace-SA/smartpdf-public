import sys, unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from source_phrases import recover


def word(text, l, r, top=10, bottom=20):
    return dict(text=text, x0=l, x1=r, top=top, bottom=bottom, upright=True)


def page(words):
    return SimpleNamespace(extract_words=lambda **kwargs: words)


class SourcePhraseTests(unittest.TestCase):
    def test_superscript_word_grouping_does_not_remove_parser_boundary(self):
        first = word("Sample", 10, 40)
        second = word("label12", 42, 77)
        first["chars"] = [dict(text=ch, size=10) for ch in "Sample"]
        second["chars"] = [
            dict(text=ch, size=10 if i < 5 else 6) for i, ch in enumerate("label12")
        ]
        self.assertEqual(
            recover(
                "Sample label 12",
                [14, 10, 74, 20],
                page([first, second]),
                [0, 0, 200, 200],
            ),
            "Sample label 12",
        )

    def test_native_punctuation_in_clipped_complete_phrase(self):
        p = page([word("2015–16", 10, 45), word("to", 47, 55), word("2021–22", 57, 92)])
        self.assertEqual(
            recover("2015-16 to 2021-22", [14, 10, 86, 20], p, [0, 0, 200, 200]),
            "2015–16 to 2021–22",
        )

    def test_numeric_and_letter_changes_are_never_guessed(self):
        p = page([word("Total", 10, 32), word("42", 35, 45)])
        for text in ["Total 43", "Totals 42"]:
            self.assertEqual(recover(text, [12, 10, 43, 20], p, [0, 0, 200, 200]), text)

    def test_extra_word_inside_box_must_not_be_discarded(self):
        p = page([word("A", 10, 15), word("99", 18, 28), word("B", 30, 35)])
        self.assertEqual(recover("A B", [10, 10, 35, 20], p, [0, 0, 200, 200]), "A B")

    def test_large_column_gap_is_not_rebuilt_as_phrase(self):
        p = page([word("A–B", 10, 25), word("C–D", 70, 85)])
        self.assertEqual(
            recover("A-B C-D", [10, 10, 85, 20], p, [0, 0, 200, 200]), "A-B C-D"
        )

    def test_two_rows_are_not_collapsed(self):
        p = page([word("A–B", 10, 25), word("C–D", 28, 43, 22, 32)])
        self.assertEqual(
            recover("A-B C-D", [10, 10, 43, 32], p, [0, 0, 200, 200]), "A-B C-D"
        )

    def test_visible_crop_is_enforced(self):
        p = page([word("A–B", 10, 25), word("C–D", 28, 43)])
        self.assertEqual(
            recover("A-B C-D", [10, 10, 43, 20], p, [0, 0, 40, 200]), "A-B C-D"
        )

    def test_large_word_overhang_is_not_accepted(self):
        p = page([word("A–B", 10, 60), word("C–D", 63, 78)])
        self.assertEqual(
            recover("A-B C-D", [33, 10, 78, 20], p, [0, 0, 200, 200]), "A-B C-D"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
