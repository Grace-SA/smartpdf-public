from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import write_workbook
from source_bidi import reading_order


class BidiDirectionTests(unittest.TestCase):
    def test_mixed_script_workbook_preserves_values_columns_and_direction(self):
        values = [
            "اسمي Jeremy في الانجليزية",
            "Jeremy is جرمي in Arabic",
            "1234",
            "אבג Example",
        ]
        table = dict(
            page=1,
            index=1,
            widths=[240, 240],
            heights=[35, 35],
            cells=[
                dict(r=i // 2, c=i % 2, rs=1, cs=1, text=value)
                for i, value in enumerate(values)
            ],
        )
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "mixed.xlsx"
            write_workbook([table], output, "tables")
            book = load_workbook(output)
            self.assertEqual(
                [book.active.cell(i // 2 + 1, i % 2 + 1).value for i in range(4)],
                values,
            )
            self.assertEqual(
                [
                    book.active.cell(i // 2 + 1, i % 2 + 1).alignment.readingOrder
                    for i in range(4)
                ],
                [2, 1, 0, 2],
            )
            self.assertEqual((book.active.max_row, book.active.max_column), (2, 2))
            book.close()
            with zipfile.ZipFile(output) as archive:
                styles = ET.fromstring(archive.read("xl/styles.xml"))
                directions = {
                    a.get("readingOrder")
                    for a in styles.iter()
                    if a.tag.endswith("}alignment")
                }
                self.assertTrue({"1", "2"}.issubset(directions))

    def test_leading_numbers_and_punctuation_do_not_replace_first_strong_direction(
        self,
    ):
        self.assertEqual(reading_order("123 - اسم Example"), 2)
        self.assertEqual(reading_order("(Example) اسم"), 1)
        self.assertEqual(reading_order("עברית 12.50"), 2)

    def test_existing_explicit_bidi_controls_are_not_overridden(self):
        for value in [
            "\u202aاسم ABC\u202c",
            "\u2067اسم ABC\u2069",
            "\u202eABC اسم\u202c",
        ]:
            self.assertEqual(reading_order(value), 0)

    def test_unmixed_ltr_numbers_cjk_and_empty_values_keep_default(self):
        for value in ["", "1234", "-1.20", "English text", "中文", "Журнал"]:
            self.assertEqual(reading_order(value), 0)
