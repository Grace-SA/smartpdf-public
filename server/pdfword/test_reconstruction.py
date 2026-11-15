"""V2 output invariants; v1 refusals remain frozen in test_worker.py."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from docx import Document
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, ArrayObject, NumberObject
from model import Rejected, table_from_html, validate
from ocr import normalize, parse_u2
from worker import convert, parse_pdf
from exporter import export_word
from layout import link_tables
from test_worker import fixture


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pdf"
        self.output = self.root / "output.docx"

    def tearDown(self):
        self.temp.cleanup()

    def test_overlapping_ocr_list_regions_do_not_duplicate_lines(self):
        records = [
            dict(label="text", bbox=[100, 100, 400, 400], content="Alpha 123\nBeta 456\nGamma 789"),
            dict(label="text", bbox=[102, 105, 390, 195], content="Alpha   123"),
            dict(label="text", bbox=[102, 205, 390, 395], content="Beta 456\nGamma 789"),
        ]
        blocks = normalize(records, 600, 800, "oxr")
        self.assertEqual([b["text"] for b in blocks], [records[0]["content"]])
        # Layout order is retained even when a small region preceded its parent.
        self.assertEqual(normalize(records[1:] + records[:1], 600, 800, "oxr"), blocks)

    def test_legitimate_repetitions_and_unique_ocr_content_survive(self):
        parent = dict(label="text", bbox=[100, 100, 400, 400], content="Repeated\nMiddle\nLast")
        for child in [
            dict(label="text", bbox=[110, 305, 390, 395], content="Repeated"),
            dict(label="text", bbox=[500, 105, 790, 195], content="Repeated"),
            dict(label="text", bbox=[110, 105, 390, 195], content="Repeated 123"),
            dict(label="text", bbox=[110, 105, 390, 195], content="Repeat"),
        ]:
            with self.subTest(child=child):
                self.assertEqual(len(normalize([parent, child], 600, 800, "oxr")), 2)

    def test_duplicate_ocr_region_requires_same_physical_location(self):
        first = dict(label="text", bbox=[100, 100, 400, 150], content="Same label")
        same = dict(first, bbox=[101, 100, 399, 150])
        adjacent = dict(first, bbox=[100, 160, 400, 210])
        result = normalize([first, same, adjacent], 600, 800, "oxr")
        self.assertEqual(len(result), 2)
        self.assertEqual([b["text"] for b in result], ["Same label", "Same label"])

    def test_repeated_lines_keep_multiplicity_in_ocr_parent_region(self):
        records = [
            dict(label="text", bbox=[100, 100, 400, 400], content="Again\nMiddle\nAgain"),
            dict(label="text", bbox=[101, 305, 399, 395], content="Again"),
        ]
        result = normalize(records, 600, 800, "oxr")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"].splitlines().count("Again"), 2)

    def test_side_by_side_figures_remain_on_one_line(self):
        from PIL import Image
        from docx.oxml.ns import qn

        for name, color in (("left.png", "blue"), ("right.png", "orange")):
            Image.new("RGB", (60, 60), color).save(self.root / name)
        blocks = [dict(id="title", kind="paragraph", text="Two figures", bbox=[36, 20, 200, 40])]
        for key, asset, bounds in (("left", "left.png", [36, 60, 136, 160]),
                                   ("right", "right.png", [200, 60, 300, 160]),
                                   ("below", "left.png", [36, 200, 136, 300])):
            blocks.append(dict(id=key, kind="image", asset=asset, bbox=bounds))
        report = export_word(dict(schema=2, pages=[dict(index=0, width=612, height=792, blocks=blocks)]), self.output, self.root)
        doc = Document(self.output)
        self.assertEqual(report["images"], 3)
        self.assertEqual([len(list(p._p.iter(qn("a:blip")))) for p in doc.paragraphs], [0, 2, 1])
        tabs = doc.paragraphs[1].paragraph_format.tab_stops
        self.assertAlmostEqual(tabs[0].position.pt, 164, places=1)

    def test_crop_and_edit(self):
        fixture(self.source, crop=True)
        report = convert(self.source, self.output)
        self.assertEqual((report["schema"], report["pages"]), (2, 1))
        doc = Document(self.output)
        self.assertAlmostEqual(doc.sections[0].page_width.pt, 580, places=1)
        doc.paragraphs[0].add_run(" edited")
        doc.save(self.root / "edited.docx")
        self.assertIn(
            "Editable 123.45 edited",
            Document(self.root / "edited.docx").paragraphs[0].text,
        )

    def test_columns_follow_reading_order(self):
        fixture(
            self.source,
            content=b"BT /F1 12 Tf 48 740 Td (L1) Tj 0 -20 Td (L2) Tj ET BT /F1 12 Tf 330 740 Td (R1) Tj 0 -20 Td (R2) Tj ET",
        )
        convert(self.source, self.output)
        text = " ".join(p.text for p in Document(self.output).paragraphs)
        self.assertEqual(
            sorted(["L1", "L2", "R1", "R2"], key=text.index), ["L1", "L2", "R1", "R2"]
        )

    def test_offset_three_columns_use_real_gutters(self):
        from columns import column_flow
        blocks = [dict(kind="paragraph", text=f"{name}{row}",
                       bbox=[left, 100 + row * 40, right, 125 + row * 40])
                  for row in range(2)
                  for name, left, right in [("L", 54, 404), ("M", 425, 775), ("R", 796, 1146)]]
        result = column_flow(blocks, 1200)
        self.assertEqual(result[0]["kind"], "columns_start")
        self.assertEqual(result[0]["count"], 3)
        self.assertEqual([b["text"] for b in result if "text" in b], ["L0", "L1", "M0", "M1", "R0", "R1"])
        # A full-width figure intersecting the text is still ambiguous.
        overlapping = dict(kind="image", bbox=[40, 110, 1160, 130])
        self.assertEqual(column_flow(blocks + [overlapping], 1200), blocks + [overlapping])

    def test_native_table_is_editable_cells(self):
        commands = b"48 600 m 300 600 l S 48 630 m 300 630 l S 48 660 m 300 660 l S 48 600 m 48 660 l S 170 600 m 170 660 l S 300 600 m 300 660 l S "
        for x, y, text in [
            (55, 640, "A"),
            (180, 640, "B"),
            (55, 610, "12.34"),
            (180, 610, "-56.78"),
        ]:
            commands += f"BT /F1 12 Tf {x} {y} Td ({text}) Tj ET ".encode()
        fixture(self.source, content=commands)
        report = convert(self.source, self.output)
        self.assertEqual(report["tables"], 1)
        doc = Document(self.output)
        self.assertEqual(
            [[c.text for c in r.cells] for r in doc.tables[0].rows],
            [["A", "B"], ["12.34", "-56.78"]],
        )
        doc.tables[0].cell(1, 0).text = "99"
        doc.save(self.root / "edited.docx")
        self.assertEqual(
            Document(self.root / "edited.docx").tables[0].cell(1, 0).text, "99"
        )

    def test_fine_merged_grid_reserves_word_cell_padding_without_overflow(self):
        from docx.oxml.ns import qn

        table = table_from_html(
            '<table><tr><td colspan="2">Header</td><td>Amount</td></tr>'
            "<tr><td></td><td>Item</td><td>123.45</td></tr></table>"
        )
        table.update(
            id="fine-grid",
            kind="table",
            bbox=[36, 36, 576, 120],
            widths=[0.001, 1, 9],
        )
        export_word(
            dict(
                schema=2, pages=[dict(index=0, width=612, height=792, blocks=[table])]
            ),
            self.output,
            self.root,
        )
        result = Document(self.output).tables[0]
        widths = [c.width.pt for c in result.columns]
        self.assertGreaterEqual(min(widths), 2)
        self.assertLessEqual(sum(widths), 540.1)
        margins = result._tbl.tblPr.find(qn("w:tblCellMar"))
        padding = sum(
            int(margins.find(qn("w:" + s)).get(qn("w:w"))) for s in ("left", "right")
        )
        self.assertLessEqual(padding + 40, min(widths) * 20)
        self.assertEqual(result.cell(0, 0)._tc, result.cell(0, 1)._tc)
        self.assertEqual(result.cell(1, 2).text, "123.45")

    def test_ocr_grid_gives_long_notes_room_without_distorting_merged_title(self):
        notes = "Review the reported values and retain the complete explanation. " * 8
        table = table_from_html(
            '<table><tr><th colspan="3">Inspection results</th></tr>'
            "<tr><th>ID</th><th>Date</th><th>Notes</th></tr>"
            f"<tr><td>001</td><td>2026-01-02</td><td>{notes}</td></tr></table>"
        )
        table.update(id="notes", kind="table", bbox=[36, 36, 576, 360])
        export_word(
            dict(
                schema=2, pages=[dict(index=0, width=612, height=792, blocks=[table])]
            ),
            self.output,
            self.root,
        )
        result = Document(self.output).tables[0]
        widths = [c.width.pt for c in result.columns]
        self.assertAlmostEqual(sum(widths), 540, delta=0.15)
        self.assertGreater(widths[2], 3 * widths[0])
        self.assertGreater(widths[2], 2 * widths[1])
        self.assertEqual(result.cell(0, 0)._tc, result.cell(0, 2)._tc)
        self.assertEqual(result.cell(2, 0).text, "001")
        self.assertEqual(result.cell(2, 1).text, "2026-01-02")
        self.assertEqual(result.cell(2, 2).text, notes.strip())

    def test_ocr_continuation_keeps_one_consistent_preferred_grid(self):
        from exporter import add_table

        document = Document()
        first = table_from_html(
            "<table><tr><th>ID</th><th>Notes</th></tr>"
            "<tr><td>001</td><td>Short note</td></tr></table>"
        )
        second = table_from_html(
            "<table><tr><th>ID</th><th>Notes</th></tr>"
            "<tr><td>002</td><td>" + "Long explanation. " * 30 + "</td></tr></table>"
        )
        second["repeat_header"] = True
        table = add_table(document, first, 540)
        widths = [column.width for column in table.columns]
        add_table(document, second, 540, table)
        self.assertEqual([column.width for column in table.columns], widths)
        self.assertEqual(len(table.rows), 3)
        for row in table.rows:
            self.assertEqual([cell.width for cell in row.cells], widths)
        self.assertEqual(table.cell(2, 0).text, "002")

    def test_hidden_layer_is_replaced_by_ocr_once(self):
        fixture(
            self.source,
            content=b"BT /F1 12 Tf 3 Tr 48 750 Td (STALE HIDDEN TEXT) Tj ET",
        )
        blocks = normalize(
            [dict(label="text", bbox=[50, 50, 600, 100], content="VISIBLE OCR 123")],
            612,
            792,
            "u2",
        )
        with patch("worker.OCR.recognize", return_value=blocks) as recognize:
            report = convert(self.source, self.output)
        recognize.assert_called_once()
        self.assertEqual(len(report["warnings"]), 1)
        text = " ".join(p.text for p in Document(self.output).paragraphs)
        self.assertEqual(text, "VISIBLE OCR 123")
        self.assertNotIn("HIDDEN", text)

    def test_borderless_numeric_grid_keeps_decimals_and_source_font(self):
        commands = b""
        for r, values in enumerate(
            (
                ("Item", "Amount"),
                ("Alpha", "12.34"),
                ("Beta", "-56.78"),
                ("Gamma", "0.01"),
            )
        ):
            for x, value in zip((50, 180), values):
                commands += f"BT /F1 8 Tf {x} {740-r*15} Td ({value}) Tj ET ".encode()
        fixture(self.source, content=commands)
        with patch(
            "worker.OCR.recognize",
            side_effect=AssertionError("Native grid must not require OCR"),
        ):
            convert(self.source, self.output)
        table = Document(self.output).tables[0]
        self.assertEqual(
            [[c.text for c in r.cells] for r in table.rows],
            [
                ["Item", "Amount"],
                ["Alpha", "12.34"],
                ["Beta", "-56.78"],
                ["Gamma", "0.01"],
            ],
        )
        self.assertEqual(table.cell(1, 1).paragraphs[0].runs[0].font.size.pt, 8)
        self.assertEqual(
            table.cell(1, 1).paragraphs[0].paragraph_format.space_after.pt, 0
        )

    def test_word_crossing_ruling_is_split_by_glyph_geometry(self):
        commands = b"50 600 m 150 600 l S 50 620 m 150 620 l S 50 640 m 150 640 l S 50 600 m 50 640 l S 100 600 m 100 640 l S 150 600 m 150 640 l S "
        commands += (
            b"BT /F1 10 Tf 94 625 Td (AB) Tj ET BT /F1 10 Tf 94 605 Td (12) Tj ET"
        )
        fixture(self.source, content=commands)
        convert(self.source, self.output)
        table = Document(self.output).tables[0]
        self.assertEqual(
            [[c.text for c in r.cells] for r in table.rows], [["A", "B"], ["1", "2"]]
        )

    def test_borderless_text_grid_requests_structured_recognition(self):
        content = b""
        for row, names in enumerate(
            (("Alpha", "Beta", "Gamma"), ("One", "Two", "Three"))
        ):
            for col, name in enumerate(names):
                content += f"BT /F1 12 Tf {48+col*150} {740-row*20} Td ({name}) Tj ET ".encode()
        fixture(self.source, content=content)
        table = normalize(
            [
                dict(
                    label="table",
                    bbox=[50, 50, 900, 200],
                    content="<table><tr><td>Alpha</td><td>Beta</td><td>Gamma</td></tr><tr><td>One</td><td>Two</td><td>Three</td></tr></table>",
                )
            ],
            612,
            792,
            "oxr",
        )
        with patch("worker.OCR.recognize", return_value=table) as recognize:
            convert(self.source, self.output)
        recognize.assert_called_once()
        self.assertEqual(Document(self.output).tables[0].cell(1, 2).text, "Three")

    def test_page_markers_and_empty_middle_page(self):
        fixture(self.source, pages=2)
        writer = PdfWriter()
        source = PdfReader(self.source)
        writer.add_page(source.pages[0])
        writer.add_blank_page(612, 792)
        writer.add_page(source.pages[1])
        writer.write(self.root / "three.pdf")
        self.assertEqual(convert(self.root / "three.pdf", self.output)["pages"], 3)
        xml = Document(self.output)._element.xml
        self.assertEqual(xml.count('w:name="smartpdf_page_'), 3)

    def test_two_hundred_pages_preserve_body_and_markers(self):
        fixture(self.source, pages=200)
        report = convert(self.source, self.output)
        doc = Document(self.output)
        self.assertEqual(report["pages"], 200)
        self.assertEqual(sum("Editable 123.45" in p.text for p in doc.paragraphs), 200)
        self.assertEqual(doc._element.xml.count('w:name="smartpdf_page_'), 200)

    def test_view_destination_is_not_an_action(self):
        fixture(self.source)
        writer = PdfWriter(clone_from=self.source)
        writer._root_object[NameObject("/OpenAction")] = ArrayObject(
            [NumberObject(0), NameObject("/Fit")]
        )
        writer.write(self.root / "view.pdf")
        self.assertEqual(convert(self.root / "view.pdf", self.output)["pages"], 1)

    def test_cancel_and_no_overwrite(self):
        fixture(self.source)
        cancel = self.root / "cancel"
        cancel.touch()
        with self.assertRaises(Rejected):
            convert(self.source, self.output, cancel=cancel)
        self.assertFalse(self.output.exists())
        cancel.unlink()
        convert(self.source, self.output)
        before = self.output.read_bytes()
        with self.assertRaises(Rejected):
            convert(self.source, self.output)
        self.assertEqual(before, self.output.read_bytes())

    def test_html_spans_and_incomplete_refusals(self):
        value = table_from_html(
            '<table><tr><th colspan="2">Header</th></tr><tr><td>1.23</td><td>-4.56</td></tr></table>'
        )
        self.assertEqual((value["rows"], value["cols"]), (2, 2))
        self.assertEqual(value["cells"][0]["colspan"], 2)
        units = table_from_html(
            "<table><tr><td>cm<sup>2</sup> / H<sub>2</sub>O / $m^{3}$</td></tr></table>"
        )
        self.assertEqual(units["cells"][0]["text"], "cm² / H₂O / m³")
        entities = table_from_html(
            "<table><tr><td>&#65; &#x3b2; &lt;tag&gt;</td></tr></table>"
        )
        self.assertEqual(entities["cells"][0]["text"], "A β <tag>")
        for bad in [
            "<table><tr><td>x",
            "<table><tr><td>x</td><td>y</td></tr><tr><td>z</td></tr></table>",
            '<table><tr><td rowspan="999">x</td></tr></table>',
            "<table><tr><td><script>x</script></td></tr></table>",
            "<!DOCTYPE table><table><tr><td>x</td></tr></table>",
            "<table><tr><td>&#0;</td></tr></table>",
            "<table><tr><td>&#xD800;</td></tr></table>",
        ]:
            with self.subTest(bad=bad), self.assertRaises(Rejected):
                table_from_html(bad)

    def test_ocr_contract_refuses_unstructured_and_invalid_positions(self):
        with self.assertRaises(Rejected):
            parse_u2("ordinary text with no region")
        with self.assertRaises(Rejected):
            normalize(
                [dict(label="text", bbox=[0, 0, 1100, 100], content="x")],
                612,
                792,
                "u2",
            )
        blocks = parse_u2("<PAGE><BLOCK>text[10,20,900,100]<FORK>Content 123")
        self.assertEqual(normalize(blocks[0], 612, 792, "u2")[0]["text"], "Content 123")
        self.assertEqual(
            normalize(
                [dict(label="page-footer", bbox=[10, 900, 900, 990], content="7")],
                612,
                792,
                "oxr",
            )[0]["kind"],
            "footer",
        )

    def test_invalid_grid_rejected_before_export(self):
        fixture(self.source)
        model = parse_pdf(self.source, self.root)
        model["pages"][0]["blocks"][0].update(
            kind="table",
            rows=2,
            cols=2,
            cells=[dict(row=0, col=0, rowspan=1, colspan=1, text="x")],
        )
        with self.assertRaises(Rejected):
            export_word(model, self.output, self.root)
        self.assertFalse(self.output.exists())

    def test_release_gate_does_not_count_generation_as_accuracy(self):
        from acceptance import evaluate

        report = evaluate(
            {
                "documents": [
                    {
                        "family": "synthetic",
                        "pages": 200,
                        "status": "generated_needs_review",
                        "categories": ["scans"],
                    }
                ]
            }
        )
        self.assertFalse(report["ready"])
        self.assertEqual(report["accepted"], 0)
        self.assertTrue(any("95%" in s for s in report["failures"]))

    def test_release_gate_refuses_missing_and_nonfinite_metrics(self):
        from acceptance import evaluate

        row = dict(
            family="synthetic",
            pages=10,
            status="accepted",
            independent_opc=True,
            visual_review=True,
            edit_reopen=True,
            ground_truth_verified=True,
            metrics={"cer": float("nan"), "reading_order": 1, "critical_errors": 0},
        )
        self.assertEqual(evaluate({"documents": [row]})["accepted"], 0)

    def test_cross_page_table_preserves_rows_and_skips_only_repeated_header(self):
        pages = []
        for i, value in enumerate(("12.34", "56.78")):
            table = table_from_html(
                "<table><tr><th>Item</th><th>Amount</th></tr><tr><td>A</td><td>"
                + value
                + "</td></tr></table>"
            )
            table.update(
                id=f"t{i}", kind="table", bbox=[40, 50, 570, 740], widths=[1, 1]
            )
            pages.append(dict(index=i, width=612, height=792, blocks=[table]))
        link_tables(pages)
        report = export_word(dict(schema=2, pages=pages), self.output, self.root)
        self.assertEqual(report["tables"], 1)
        table = Document(self.output).tables[0]
        self.assertEqual(
            [[c.text for c in r.cells] for r in table.rows],
            [["Item", "Amount"], ["A", "12.34"], ["A", "56.78"]],
        )
        self.assertEqual(
            Document(self.output)._element.xml.count('w:name="smartpdf_page_'), 2
        )

    def test_local_continuation_caption_does_not_require_document_wide_repetition(self):
        pages = [dict(index=0, width=612, height=792, blocks=[dict(id="intro", kind="paragraph", bbox=[40, 40, 500, 80], text="Introduction")])]
        for i, value in enumerate(("12.34", "56.78"), 1):
            table = table_from_html(f"<table><tr><td>A</td><td>{value}</td></tr></table>")
            table.update(id=f"table-{i}", kind="table", bbox=[40, 90, 570, 740], widths=[1, 1])
            title = dict(id=f"title-{i}", kind="heading", bbox=[40, 30, 500, 55], text="Measurements" + (" continued" if i == 2 else ""))
            pages.append(dict(index=i, width=612, height=792, blocks=[title, table]))
        link_tables(pages)
        report = export_word(dict(schema=2, pages=pages), self.output, self.root)
        self.assertEqual(report["tables"], 1)
        document = Document(self.output)
        self.assertEqual([[c.text for c in row.cells] for row in document.tables[0].rows], [["A", "12.34"], ["A", "56.78"]])
        self.assertEqual(document._element.xml.count('w:name="smartpdf_page_'), 3)

    def test_independent_adjacent_tables_remain_separate_in_word(self):
        blocks = []
        for i, value in enumerate(("12.34", "56.78", "90.12")):
            table = table_from_html(f"<table><tr><td>{value}</td></tr></table>")
            table.update(
                id=f"t{i}", kind="table", bbox=[40, 50 + i * 80, 570, 100 + i * 80]
            )
            blocks.append(table)
        report = export_word(
            dict(schema=2, pages=[dict(index=0, width=612, height=792, blocks=blocks)]),
            self.output,
            self.root,
        )
        document = Document(self.output)
        self.assertEqual(report["tables"], 3)
        self.assertEqual(
            [t.cell(0, 0).text for t in document.tables], ["12.34", "56.78", "90.12"]
        )
        self.assertEqual(
            [element.tag.rsplit("}", 1)[-1] for element in document.element.body],
            ["tbl", "p", "tbl", "p", "tbl", "sectPr"],
        )


if __name__ == "__main__":
    unittest.main()
