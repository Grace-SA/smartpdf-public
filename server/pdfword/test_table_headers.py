"""Semantic multirow headers must not discard repeated source data."""

import copy
import tempfile
import unittest
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from exporter import export_word, add_table
from layout import link_tables
from model import Rejected, table_from_html, table_header_rows
from pypdf import PdfWriter
from test_worker import fixture
from worker import convert


def pages_for(*html):
    pages = []
    for i, markup in enumerate(html):
        table = table_from_html(markup)
        table.update(id=f"table-{i}", kind="table", bbox=[40, 50, 570, 740], widths=[1] * table["cols"])
        pages.append(dict(index=i, width=612, height=792, blocks=[table]))
    return pages


def table(body):
    return f"<table>{body}</table>"


class TableHeaderTests(unittest.TestCase):
    def test_native_multipage_pdf_retains_repeated_data_without_ocr(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            output = root / "result.docx"
            writer = PdfWriter()
            for index in range(2):
                commands = b""
                for y in (50, 400, 740):
                    commands += f"40 {y} m 570 {y} l S ".encode()
                for x in (40, 300, 570):
                    commands += f"{x} 50 m {x} 740 l S ".encode()
                for x, y, value in [(50, 710, "A"), (310, 710, "12.34"), (50, 370, "B"), (310, 370, str(index + 1))]:
                    commands += f"BT /F1 12 Tf {x} {y} Td ({value}) Tj ET ".encode()
                page = root / f"page-{index}.pdf"
                fixture(page, content=commands)
                writer.append(page)
            writer.write(source)
            with patch("worker.OCR.recognize", side_effect=AssertionError("native table should not need OCR")):
                report = convert(source, output)
            self.assertEqual(report["pages"], 2)
            doc = Document(output)
            self.assertEqual(len(doc.tables), 2)
            self.assertEqual([t.cell(0, 1).text for t in doc.tables], ["12.34", "12.34"])
            self.assertEqual([t.cell(1, 1).text for t in doc.tables], ["1", "2"])

    def test_identical_data_first_rows_are_not_removed_as_headers(self):
        pages = pages_for(*[table('<tr><td>A</td><td>12.34</td></tr><tr><td>B</td><td>56.78</td></tr>')] * 2)
        link_tables(pages)
        self.assertNotIn("continues", pages[1]["blocks"][0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.docx"
            export_word(dict(schema=2, pages=pages), path, directory)
            doc = Document(path)
            self.assertEqual(len(doc.tables), 2)
            self.assertEqual([t.cell(0, 1).text for t in doc.tables], ["12.34", "12.34"])

    def test_explicit_continuation_keeps_identical_data_rows(self):
        pages = pages_for(*[table('<tr><td>A</td><td>12.34</td></tr><tr><td>B</td><td>56.78</td></tr>')] * 2)
        pages[1]["blocks"][0]["continuation"] = True
        link_tables(pages)
        self.assertEqual(pages[1]["blocks"][0]["repeat_header_rows"], 0)
        doc = Document()
        first = add_table(doc, pages[0]["blocks"][0], 540)
        add_table(doc, pages[1]["blocks"][0], 540, first)
        self.assertEqual([r.cells[1].text for r in first.rows], ["12.34", "56.78", "12.34", "56.78"])

    def test_two_row_merged_headers_are_repeated_once(self):
        head = '<tr><th rowspan="2">Item</th><th colspan="2">Totals</th></tr><tr><th>2025</th><th>2026</th></tr>'
        pages = pages_for(*[table(head + f'<tr><td>{label}</td><td>{x}</td><td>{y}</td></tr>') for label, x, y in [("A", "12.34", "56.78"), ("B", "90.12", "34.56")]])
        link_tables(pages)
        second = pages[1]["blocks"][0]
        self.assertEqual(second["repeat_header_rows"], 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "merged.docx"
            export_word(dict(schema=2, pages=pages), path, directory)
            doc = Document(path)
            self.assertEqual(len(doc.tables), 1)
            output = doc.tables[0]
            self.assertEqual(len(output.rows), 4)
            self.assertEqual([output.cell(r, 0).text for r in (2, 3)], ["A", "B"])
            self.assertEqual([output.cell(3, c).text for c in range(3)], ["B", "90.12", "34.56"])
            self.assertEqual(output.cell(0, 0)._tc, output.cell(1, 0)._tc)
            self.assertEqual(output.cell(0, 1)._tc, output.cell(0, 2)._tc)
            self.assertEqual([r._tr.get_or_add_trPr().find(qn("w:tblHeader")) is not None for r in output.rows], [True, True, False, False])
            self.assertEqual(doc._element.xml.count('w:name="smartpdf_page_'), 2)
            output.cell(3, 2).text = "99.00"
            doc.save(path)
            self.assertEqual(Document(path).tables[0].cell(3, 2).text, "99.00")

    def test_same_first_header_different_second_header_is_not_dropped(self):
        first = '<tr><th colspan="2">Totals</th></tr>'
        pages = pages_for(*[table(first + f'<tr><th>Item</th><th>{year}</th></tr><tr><td>A</td><td>12</td></tr>') for year in (2025, 2026)])
        link_tables(pages)
        self.assertNotIn("continues", pages[1]["blocks"][0])

    def test_same_text_different_merge_structure_is_not_dropped(self):
        a = '<tr><th colspan="2">Totals</th><th>Other</th></tr><tr><td>A</td><td>B</td><td>C</td></tr>'
        b = '<tr><th>Totals</th><th colspan="2">Other</th></tr><tr><td>D</td><td>E</td><td>F</td></tr>'
        pages = pages_for(table(a), table(b))
        link_tables(pages)
        self.assertNotIn("continues", pages[1]["blocks"][0])

    def test_thead_cells_are_semantic_headers(self):
        value = table_from_html(table('<thead><tr><td>Item</td><td>Amount</td></tr></thead><tbody><tr><td>A</td><td>12</td></tr></tbody>'))
        self.assertEqual(table_header_rows(value), 1)
        self.assertEqual([c["header"] for c in value["cells"]], [True, True, False, False])

    def test_header_span_into_body_is_not_a_removable_prefix(self):
        value = table_from_html(table('<tr><th rowspan="2">Item</th><th>Value</th></tr><tr><td>12</td></tr>'))
        self.assertEqual(table_header_rows(value), 0)

    def test_header_only_followup_is_not_removed_entirely(self):
        header = '<tr><th>Item</th><th>Amount</th></tr>'
        pages = pages_for(table(header + '<tr><td>A</td><td>12</td></tr>'), table(header))
        link_tables(pages)
        self.assertNotIn("continues", pages[1]["blocks"][0])

    def test_invalid_skip_or_split_merge_rejected(self):
        value = table_from_html(table('<tr><th rowspan="2">Item</th><th>Value</th></tr><tr><td>12</td></tr>'))
        for count in (1, 2, -1, True, 0.5):
            with self.subTest(count=count):
                block = copy.deepcopy(value)
                block["repeat_header_rows"] = count
                doc = Document()
                existing = add_table(doc, value, 540)
                with self.assertRaises(Rejected):
                    add_table(doc, block, 540, existing)

    def test_stale_repeat_metadata_cannot_remove_data_rows(self):
        value = table_from_html(table('<tr><td>A</td><td>12.34</td></tr><tr><td>B</td><td>56.78</td></tr>'))
        doc = Document()
        existing = add_table(doc, value, 540)
        value["repeat_header_rows"] = 1
        with self.assertRaisesRegex(Rejected, "discard table data"):
            add_table(doc, value, 540, existing)


if __name__ == "__main__":
    unittest.main()
