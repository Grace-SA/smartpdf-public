"""OCR HTML table content must survive as editable text, never concatenated values."""

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from lxml import etree

from exporter import export_word
from model import Rejected, table_from_html


class TableContentTests(unittest.TestCase):
    def parse_cell(self, markup):
        return table_from_html(f"<table><tr><td>{markup}</td></tr></table>")["cells"][0]["text"]

    def test_paragraphs_do_not_concatenate_amounts(self):
        self.assertEqual(self.parse_cell("<p>12.34</p><p>-56.78</p>"), "12.34\n-56.78")

    def test_inline_formatting_does_not_split_numbers(self):
        self.assertEqual(self.parse_cell("<b>12</b><span>.</span><i>34</i>"), "12.34")

    def test_paragraphs_keep_leading_and_trailing_text(self):
        self.assertEqual(self.parse_cell("Before<p>Middle</p>After"), "Before\nMiddle\nAfter")

    def test_breaks_and_unicode_units_are_preserved(self):
        self.assertEqual(
            self.parse_cell("<p>面积 m<sup>2</sup><br>H<sub>2</sub>O</p><p>−12.34</p>"),
            "面积 m²\nH₂O\n−12.34",
        )

    def test_inline_superscript_tail_is_preserved(self):
        self.assertEqual(self.parse_cell("x<sup><b>2</b></sup> + y<sub>1</sub>"), "x² + y₁")

    def test_multiple_breaks_remain_multiple_breaks(self):
        self.assertEqual(self.parse_cell("A<br><br>B"), "A\n\nB")

    def test_non_numeric_superscript_is_not_dropped(self):
        self.assertEqual(self.parse_cell("x<sup>abc</sup>y"), "xabcy")

    def test_scripts_cannot_concatenate_line_separated_digits(self):
        self.assertEqual(self.parse_cell("x<sup>1<br>2</sup>"), "x1\n2")
        self.assertEqual(self.parse_cell("x<sub><p>1</p><p>2</p></sub>"), "x\n1\n2")

    def test_formatting_whitespace_after_paragraph_is_not_a_blank_line(self):
        self.assertEqual(self.parse_cell("<p>12</p>\n  <p>34</p>"), "12\n34")

    def test_structural_text_is_rejected_instead_of_silently_lost(self):
        for markup in (
            "<table>Lost<tr><td>A</td></tr></table>",
            "<table><tr>Lost<td>A</td></tr></table>",
            "<table><tr><td>A</td>Lost</tr></table>",
            "<table><tbody>Lost<tr><td>A</td></tr></tbody></table>",
            "<table><tr><td>A</td></tr><p>Lost note</p></table>",
            "<table><tr><td>A</td></tr><span>Lost</span></table>",
        ):
            with self.subTest(markup=markup), self.assertRaises(Rejected):
                table_from_html(markup)

    def test_structural_whitespace_and_groups_are_supported(self):
        table = table_from_html(
            "<table>\n<thead><tr><th>Header</th></tr></thead>\n"
            "<tbody>\n<tr><td><p>12</p><p>34</p></td></tr>\n</tbody></table>"
        )
        self.assertEqual([c["text"] for c in table["cells"]], ["Header", "12\n34"])

    def test_export_edit_reopen_and_xml_keep_lines_and_merged_owner(self):
        table = table_from_html(
            '<table><tr><th colspan="2"><p>Revenue</p><p>2026</p></th></tr>'
            '<tr><td><p>12.34</p><p>-56.78</p></td><td>m<sup>2</sup></td></tr></table>'
        )
        table.update(id="synthetic-table", kind="table", bbox=[36, 36, 576, 200])
        model = dict(schema=2, pages=[dict(index=0, width=612, height=792, blocks=[table])])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "table.docx"
            export_word(model, output, root)
            document = Document(output)
            self.assertEqual(document.tables[0].cell(1, 0).text, "12.34\n-56.78")
            self.assertEqual(document.tables[0].cell(0, 0)._tc, document.tables[0].cell(0, 1)._tc)
            document.tables[0].cell(1, 1).text += " edited"
            document.save(output)
            self.assertEqual(Document(output).tables[0].cell(1, 1).text, "m² edited")
            with ZipFile(output) as archive:
                xml = etree.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            cells = xml.xpath("//w:tbl/w:tr/w:tc", namespaces=ns)
            amounts = cells[1].xpath(".//w:t/text()", namespaces=ns)
            self.assertEqual(amounts, ["12.34", "-56.78"])
            self.assertEqual(len(cells[1].xpath(".//w:br", namespaces=ns)), 1)


if __name__ == "__main__":
    unittest.main()
