"""Public synthetic adapter invariants, including silent data loss and fallback."""
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from lxml import etree as E
from model import Rejected
from test_worker import fixture
from stirling_native import check_coverage, check_visual_coverage, profile
from stirling_package import normalize_package, W, w
from worker import convert
from worker import needs_ocr
import pypdfium2 as pdf
from contextlib import closing
from text_geometry import glyph_geometry, ink_bounds


class NonSeeking(io.BytesIO):
    def seek(self, *args):
        raise io.UnsupportedOperation("stream")


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def raw(self, content, *, pages=1, extra=None):
        body = f'<w:document xmlns:w="{W}"><w:body>{content}<w:sectPr><w:pgSz w:w="12000" w:h="16000"/><w:pgMar w:left="1000" w:right="6000"/></w:sectPr></w:body></w:document>'
        stream = NonSeeking()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", body)
            archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            for name, value in (extra or {}).items():
                archive.writestr(name, value)
        path = self.root / "raw.docx"
        path.write_bytes(stream.getvalue())
        return path

    def test_descriptor_zip_and_leading_table_are_preserved(self):
        table = '<w:tbl><w:tblGrid><w:gridCol w:w="11000"/></w:tblGrid><w:tr><w:tc><w:p><w:r><w:t>Balance 123.45</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        raw = self.raw(table + '<w:p><w:bookmarkStart w:id="1" w:name="_Pg1"/><w:r><w:t>End</w:t></w:r></w:p>')
        out = self.root / "result.docx"
        report, text = normalize_package(raw, out, 1)
        self.assertIn("Balance 123.45", text[0])
        self.assertEqual(report["tables"], 1)
        with zipfile.ZipFile(raw) as z:
            self.assertTrue(z.infolist()[0].flag_bits & 8)
        with zipfile.ZipFile(out) as z:
            self.assertFalse(any(i.flag_bits & 8 for i in z.infolist()))
            tree = E.fromstring(z.read("word/document.xml"))
        self.assertEqual(tree.find('.//' + w('gridCol')).get(w('w')), '10280')
        self.assertEqual(tree.find('.//' + w('bookmarkStart')).get(w('name')), 'smartpdf_page_1')

    def test_missing_page_or_external_relationship_is_refused(self):
        raw = self.raw('<w:p><w:bookmarkStart w:id="1" w:name="_Pg1"/></w:p>')
        with self.assertRaisesRegex(ValueError, "bookmarks"):
            normalize_package(raw, self.root / "a.docx", 2)
        raw = self.raw('<w:p><w:bookmarkStart w:id="1" w:name="_Pg1"/></w:p>', extra={
            'word/_rels/document.xml.rels': '<Relationships><Relationship Id="r1" Target="https://example.com" TargetMode="External"/></Relationships>'})
        with self.assertRaisesRegex(ValueError, "External"):
            normalize_package(raw, self.root / "b.docx", 1)

    def test_numeric_loss_and_duplicate_page_content_cannot_pass(self):
        with self.assertRaises(ValueError):
            check_coverage([dict(text="A" * 2000 + " 987.65")], ["A" * 2000 + " 987.64"])
        with self.assertRaises(ValueError):
            check_coverage([dict(text="Page ONE 123"), dict(text="Page TWO 456")], ["Page ONE 123", "Page ONE 123"])

    def test_proven_fully_clipped_number_is_excluded_without_rewriting_source(self):
        source = self.root / "clipped-number.pdf"
        fixture(source, content=(b'BT /F1 12 Tf 48 750 Td (Visible 123) Tj ET '
                                 b'q 40 500 200 200 re W n '
                                 b'BT /F1 12 Tf 350 600 Td (987654) Tj ET Q'))
        original = source.read_bytes()
        with pdf.PdfDocument(source) as document, closing(document[0]) as page:
            with closing(page.render(scale=2)) as bitmap:
                before = bitmap.to_pil().tobytes()
        pages, reason = profile(source)
        self.assertEqual(reason, "native-text")
        self.assertNotIn("987654", pages[0]["text"])
        self.assertIn("123", pages[0]["text"])
        self.assertTrue(pages[0]["excludeClippedNumbers"])
        check_coverage(pages, ["Visible 123"])
        with self.assertRaisesRegex(ValueError, "exposed excluded"):
            check_coverage(pages, ["Visible 123 987654"])
        self.assertEqual(source.read_bytes(), original)
        with pdf.PdfDocument(source) as document, closing(document[0]) as page:
            with closing(page.render(scale=2)) as bitmap:
                self.assertEqual(bitmap.to_pil().tobytes(), before)

    def test_partial_clipping_and_non_numeric_hidden_content_keep_fallback(self):
        source = self.root / "partial.pdf"
        for text, x in [(b'987654', 230), (b'Secret', 350)]:
            fixture(source, content=(b'BT /F1 12 Tf 48 750 Td (Visible 123) Tj ET '
                                     b'q 40 500 200 200 re W n BT /F1 12 Tf '
                                     + str(x).encode() + b' 600 Td (' + text + b') Tj ET Q'))
            self.assertEqual(profile(source)[1], "clipped-native-text")

    def test_clipping_geometry_alone_cannot_bypass_render_verification(self):
        source = self.root / "unverified.pdf"
        fixture(source, content=(b'BT /F1 12 Tf 48 750 Td (Visible 123) Tj ET '
                                 b'q 40 500 200 200 re W n '
                                 b'BT /F1 12 Tf 350 600 Td (987654) Tj ET Q'))
        with patch("stirling_native.confirm_invisible_numbers", return_value=False):
            self.assertEqual(profile(source)[1], "unverified-clipped-text")

    def test_hidden_text_and_known_columns_keep_existing_route(self):
        source = self.root / "source.pdf"
        fixture(source, content=b'BT /F1 12 Tf 3 Tr 48 750 Td (Invisible) Tj ET')
        self.assertEqual(profile(source)[1], "hidden-or-transparent-text")
        fixture(source, content=b'BT /F1 12 Tf 48 740 Td (L1) Tj 0 -20 Td (L2) Tj ET BT /F1 12 Tf 330 740 Td (R1) Tj 0 -20 Td (R2) Tj ET')
        self.assertEqual(profile(source)[1], "structured-columns")

    def test_nested_source_grid_keeps_structured_fallback(self):
        source = self.root / "nested.pdf"
        outer = b"50 400 500 300 re S 300 400 m 300 700 l S 50 550 m 550 550 l S "
        inner = b"80 580 160 80 re S 160 580 m 160 660 l S 80 620 m 240 620 l S "
        labels = b"BT /F1 10 Tf 350 650 Td (Outer) Tj ET BT /F1 10 Tf 100 640 Td (A) Tj ET BT /F1 10 Tf 180 640 Td (B) Tj ET BT /F1 10 Tf 100 600 Td (C) Tj ET BT /F1 10 Tf 180 600 Td (D) Tj ET"
        fixture(source, content=outer + inner + labels)
        self.assertEqual(profile(source)[1], "nested-source-grid")
        # An ordinary merged header and an independent adjacent grid are not nesting.
        fixture(source, content=outer + labels)
        self.assertNotEqual(profile(source)[1], "nested-source-grid")
        adjacent = b"50 400 200 300 re S 150 400 m 150 700 l S 50 550 m 250 550 l S 300 400 200 300 re S 400 400 m 400 700 l S 300 550 m 500 550 l S "
        fixture(source, content=adjacent + labels)
        self.assertNotEqual(profile(source)[1], "nested-source-grid")

    def test_failed_engine_falls_back_without_leaving_partial_output(self):
        source = self.root / "source.pdf"
        fixture(source)
        output = self.root / "result.docx"
        with patch.dict(os.environ, {"PDFWORD_NATIVE_ENGINE": "stirling"}), patch(
            "stirling_native.convert_native", side_effect=ValueError("synthetic engine failure")
        ):
            report = convert(source, output)
        self.assertTrue(output.exists())
        self.assertEqual(report["engine"], "structured-native")
        self.assertIn("native-fallback", report["nativeRoute"])

    def test_cancellation_is_not_retried_as_fallback(self):
        source = self.root / "source.pdf"
        fixture(source)
        output = self.root / "result.docx"
        with patch.dict(os.environ, {"PDFWORD_NATIVE_ENGINE": "stirling"}), patch(
            "stirling_native.convert_native", side_effect=Rejected("Conversion cancelled.")
        ), patch("worker.OCR") as ocr:
            with self.assertRaisesRegex(Rejected, "cancelled"):
                convert(source, output)
        ocr.assert_not_called()
        self.assertFalse(output.exists())

    def test_cosmetic_background_keeps_native_prose_and_restores_render(self):
        from text_visibility import cosmetic_white_rectangles
        from worker import parse_pdf
        source = self.root / "background.pdf"
        text = b'0 0 0 rg BT /F1 12 Tf 48 750 Td (Long editable prose over an opaque white background 1234567890.) Tj ET'
        fixture(source, content=b'1 1 1 rg 40 730 500 20.004 re f 40 750 500 20 re f ' + text)
        with pdf.PdfDocument(source) as document, closing(document[0]) as page:
            with closing(page.render(scale=2)) as bitmap:
                before = bitmap.to_pil().tobytes()
            self.assertEqual(len(cosmetic_white_rectangles(page)), 2)
            with closing(page.render(scale=2)) as bitmap:
                self.assertEqual(bitmap.to_pil().tobytes(), before)
        with patch("worker.OCR") as ocr:
            model = parse_pdf(source, self.root)
        ocr.assert_not_called()
        self.assertFalse(any(b["kind"] == "image" for b in model["pages"][0]["blocks"]))
        self.assertIn("1234567890", str(model))

    def test_white_cover_and_colored_artwork_are_not_cosmetic(self):
        from text_visibility import cosmetic_white_rectangles
        source = self.root / "cover.pdf"
        for paint in (
            b'0 0 0 rg BT /F1 12 Tf 48 750 Td (Covered confidential text) Tj ET 1 1 1 rg 40 730 500 40 re f',
            b'0 0 0 rg 40 730 500 40 re f 1 1 1 rg 40 730 500 40 re f',
            b'1 0 0 rg 40 730 500 40 re f',
            b'0 0 0 rg BT /F1 0.001 Tf 48 750 Td (Subpixel secret) Tj ET 1 1 1 rg 40 730 500 40 re f',
        ):
            with self.subTest(paint=paint):
                fixture(source, content=paint)
                with pdf.PdfDocument(source) as document, closing(document[0]) as page:
                    self.assertEqual(cosmetic_white_rectangles(page), [])

    def test_background_render_failure_restores_drawing_modes(self):
        from text_visibility import cosmetic_white_rectangles
        source = self.root / "restore.pdf"
        fixture(source, content=b'1 1 1 rg 40 730 500 40 re f')
        with pdf.PdfDocument(source) as document, closing(document[0]) as page:
            render = page.render
            calls = []
            def fail_second(*args, **kwargs):
                calls.append(1)
                if len(calls) == 2:
                    raise RuntimeError("synthetic render failure")
                return render(*args, **kwargs)
            with patch.object(page, "render", side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, "synthetic render failure"):
                    cosmetic_white_rectangles(page)
            # A second successful check must still find the restored white path.
            self.assertEqual(len(cosmetic_white_rectangles(page)), 1)

    def test_bright_text_needs_real_background_contrast(self):
        source = self.root / "source.pdf"
        for background, expected in ((b"", True), (b"0 0 0 rg 40 730 250 40 re f ", False)):
            fixture(source, content=background + b'1 1 1 rg BT /F1 12 Tf 48 750 Td (Visible white heading) Tj ET')
            with pdf.PdfDocument(source) as document, closing(document[0]) as page:
                self.assertEqual(needs_ocr(page)[0], expected)

    def test_clipped_text_is_not_exposed_by_native_route(self):
        source = self.root / "source.pdf"
        fixture(source, content=b'BT /F1 12 Tf -100 750 Td (Hidden outside page) Tj ET')
        self.assertEqual(profile(source)[1], "clipped-native-text")

    def test_rotation_does_not_force_text_to_ocr(self):
        source = self.root / "source.pdf"
        fixture(source, rotation=90)
        pages, reason = profile(source)
        self.assertEqual(reason, "native-text")
        self.assertEqual(len(pages), 1)

    def test_occluded_white_text_does_not_count_background_contrast(self):
        source = self.root / "source.pdf"
        fixture(source, content=b'0 0 0 rg 40 730 250 40 re f 1 1 1 rg BT /F1 12 Tf 48 750 Td (Covered heading) Tj ET 0 0 0 rg 40 730 250 40 re f 1 1 1 rg 50 750 10 10 re f')
        with pdf.PdfDocument(source) as document, closing(document[0]) as page:
            self.assertTrue(needs_ocr(page)[0])

    def test_unused_object_extent_does_not_turn_visible_glyphs_into_ocr(self):
        source = self.root / "source.pdf"
        fixture(source, content=b'40 730 200 40 re W n BT /F1 12 Tf 48 750 Td (Visible) Tj ET')
        # Some PDF fonts expose unused advances in the object bounding box.
        # Real character boxes, linked back to that same text object, remain inside.
        with patch.object(pdf.PdfTextObj, "get_bounds", return_value=(48, 750, 900, 760)):
            with pdf.PdfDocument(source) as document, closing(document[0]) as page:
                self.assertFalse(needs_ocr(page)[0])
            self.assertEqual(profile(source)[1], "native-text")

    def test_real_clipped_glyphs_still_require_ocr(self):
        source = self.root / "source.pdf"
        fixture(source, content=b'40 730 20 40 re W n BT /F1 12 Tf 48 750 Td (Partly clipped) Tj ET')
        with pdf.PdfDocument(source) as document, closing(document[0]) as page:
            self.assertTrue(needs_ocr(page)[0])
        self.assertEqual(profile(source)[1], "clipped-native-text")

    def test_incomplete_glyph_mapping_keeps_conservative_bounds(self):
        source = self.root / "source.pdf"
        fixture(source)
        with pdf.PdfDocument(source) as document, closing(document[0]) as page, closing(page.get_textpage()) as tp:
            obj = next(x for x in page.get_objects(textpage=tp) if x.type == pdf.raw.FPDF_PAGEOBJ_TEXT)
            geometry = glyph_geometry(tp)
            for group in geometry.values():
                group["characters"].clear()
            self.assertEqual(ink_bounds(obj, geometry), obj.get_bounds())

    def test_fully_off_page_glyphs_do_not_force_ocr_or_leak_into_output(self):
        from docx import Document
        source = self.root / "source.pdf"
        fixture(source, content=b'BT /F1 12 Tf 48 750 Td (Visible title) Tj ET BT /F1 12 Tf -1000 750 Td (Offpage secret) Tj ET')
        with pdf.PdfDocument(source) as document, closing(document[0]) as page:
            self.assertFalse(needs_ocr(page)[0])
        with patch("worker.OCR.recognize", side_effect=AssertionError("Unexpected OCR")):
            output = self.root / "result.docx"
            convert(source, output)
        text = " ".join(p.text for p in Document(output).paragraphs)
        self.assertIn("Visible title", text)
        self.assertNotIn("Offpage", text)

    def test_decimal_page_edges_survive_native_crop(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import RectangleObject
        source = self.root / "source.pdf"
        fixture(source)
        reader = PdfReader(source)
        writer = PdfWriter()
        page = writer.add_page(reader.pages[0])
        page.mediabox = RectangleObject([0, 0, 595.276, 841.89])
        with source.open("wb") as stream:
            writer.write(stream)
        with patch("worker.OCR.recognize", side_effect=AssertionError("Unexpected OCR")):
            self.assertEqual(convert(source, self.root / "result.docx")["pages"], 1)

    def test_graphics_on_another_page_do_not_cover_missing_vector_content(self):
        pages = [{"hasVisualContent": False}, {"hasVisualContent": True}]
        with self.assertRaisesRegex(ValueError, "graphics"):
            check_visual_coverage(pages, [1, 0])
        check_visual_coverage(pages, [0, 1])

    def test_native_background_picture_cannot_replace_editable_prose(self):
        from docx import Document
        source = self.root / "source.pdf"
        line = 'Shaded native paragraph needs to stay editable, including 123.45.'
        content = b'0.9 0.9 0.9 rg 40 700 450 80 re f 0 0 0 rg BT /F1 10 Tf 48 750 Td '
        content += ('(' + line + ') Tj 0 -14 Td ') .encode() * 3 + b'ET'
        fixture(source, content=content)
        with patch.dict(os.environ, {"PDFWORD_NATIVE_ENGINE": ""}), patch(
            "worker.OCR.recognize", return_value=[dict(kind="paragraph", text=' '.join([line]*3), bbox=[48, 30, 540, 100], source="ocr")]
        ) as recognize:
            output = self.root / "result.docx"
            report = convert(source, output)
        recognize.assert_called_once()
        self.assertEqual(report["engine"], "structured-ocr")
        self.assertIn(line, " ".join(p.text for p in Document(output).paragraphs))

    def test_narrow_vector_glyph_is_retained_next_to_wide_glyph(self):
        from docx import Document
        source = self.root / "source.pdf"
        fixture(source, content=b'BT /F1 12 Tf 48 750 Td (Native) Tj ET 150 740 3 24 re f 167 740 3 24 re f 153 750 14 3 re f 180 740 3 24 re f')
        with patch.dict(os.environ, {"PDFWORD_NATIVE_ENGINE": ""}), patch("worker.OCR.recognize", side_effect=AssertionError("Unexpected OCR")):
            output = self.root / "result.docx"
            convert(source, output)
        self.assertEqual(len(Document(output).inline_shapes), 2)

    def test_hairline_vector_glyph_is_retained(self):
        from docx import Document
        source = self.root / "source.pdf"
        fixture(source, content=b'BT /F1 12 Tf 48 750 Td (Native) Tj ET 150 740 3 24 re f 167 740 3 24 re f 153 750 14 3 re f 1 w 180 740 m 180 764 l S')
        with patch.dict(os.environ, {"PDFWORD_NATIVE_ENGINE": ""}), patch("worker.OCR.recognize", side_effect=AssertionError("Unexpected OCR")):
            output = self.root / "result.docx"
            convert(source, output)
        self.assertEqual(len(Document(output).inline_shapes), 2)

    def test_header_grid_and_repeated_values_recover_missing_body_rules(self):
        from docx import Document
        source = self.root / "source.pdf"
        lines = b'40 620 340 110 re S 40 700 m 380 700 l S 160 700 m 160 730 l S 230 700 m 230 730 l S 300 620 m 300 730 l S 300 669 m 380 669 l S '
        for x, y, text in [(48,710,'Item'),(175,710,'A'),(245,710,'B'),(315,710,'Missing'),(48,680,'Alpha'),(175,680,'1.2'),(245,680,'2.3'),(48,655,'Beta'),(175,655,'3.4'),(48,630,'Gamma'),(175,630,'5.6'),(245,630,'6.7')]:
            lines += f'BT /F1 10 Tf {x} {y} Td ({text}) Tj ET '.encode()
        fixture(source, content=lines)
        with patch.dict(os.environ, {"PDFWORD_NATIVE_ENGINE": ""}), patch("worker.OCR.recognize", side_effect=AssertionError("Unexpected OCR")):
            output = self.root / "result.docx"
            convert(source, output)
        table = Document(output).tables[0]
        self.assertEqual((len(table.rows), len(table.columns)), (4, 4))
        self.assertEqual([[c.text for c in row.cells] for row in table.rows], [['Item','A','B','Missing'],['Alpha','1.2','2.3',''],['Beta','3.4','',''],['Gamma','5.6','6.7','']])


if __name__ == "__main__":
    unittest.main()
