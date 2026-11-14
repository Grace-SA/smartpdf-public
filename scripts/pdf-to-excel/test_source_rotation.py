import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import ConversionError, convert
from source_rotation import prepared_rotation, unresolved_dominant_turn


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.expected = [("Code", "Amount"), ("00123", "1.234,50"), ("00007", "-12.00")]

    def source(self, angle, crop=False, mixed=False, image=False):
        raw = self.root / "raw.pdf"
        c = canvas.Canvas(str(raw), pagesize=(600, 600))
        c.setFont("Helvetica", 10)
        for x in (100, 250, 400):
            c.line(x, 300, x, 420)
        for y in (300, 340, 380, 420):
            c.line(100, y, 400, y)
        for row, values in enumerate(self.expected):
            for col, value in enumerate(values):
                c.drawString(110 + 150 * col, 400 - 40 * row, value)
        if crop:
            c.drawString(10, 550, "HIDDEN SECRET")
        if mixed:
            c.saveState()
            c.translate(450, 300)
            c.rotate(90)
            c.drawString(0, 0, "VERTICAL LEGEND")
            c.restoreState()
        if image:
            from PIL import Image
            from reportlab.lib.utils import ImageReader

            c.drawImage(
                ImageReader(Image.new("RGB", (10, 10), "red")), 100, 100, 20, 20
            )
        c.save()
        writer = PdfWriter(clone_from=raw)
        if crop:
            writer.pages[0].cropbox = RectangleObject((80, 280, 420, 440))
        writer.pages[0].rotation = angle
        source = self.root / f"{angle}.pdf"
        writer.write(source)
        return source

    def test_dominant_native_turn_is_refusal_not_majority_rotation(self):
        def glyph(angle):
            matrices = {0: (1, 0, 0, 1, 0, 0), 90: (0, 1, -1, 0, 0, 0),
                        180: (-1, 0, 0, -1, 0, 0), 270: (0, -1, 1, 0, 0, 0)}
            return dict(matrix=matrices[angle])
        for angle in (90, 180, 270):
            self.assertTrue(unresolved_dominant_turn([glyph(angle)] * 18 + [glyph(0)] * 2))
            self.assertFalse(unresolved_dominant_turn([glyph(angle)] * 17 + [glyph(0)] * 3))
            self.assertFalse(unresolved_dominant_turn([glyph(angle)] * 19))
        self.assertFalse(unresolved_dominant_turn([glyph(90)] * 5 + [glyph(0)] * 20))
        self.assertFalse(unresolved_dominant_turn([dict(matrix=(float('nan'),)*6)] * 20))
        self.assertFalse(unresolved_dominant_turn([glyph(90)] * 10 + [glyph(270)] * 10))

    def test_content_rotated_table_with_upright_footer_never_reaches_model(self):
        source = self.root / 'content-rotated.pdf'
        c = canvas.Canvas(str(source), pagesize=(600, 600))
        c.saveState(); c.translate(500, 0); c.rotate(90)
        for x in (100, 250, 400):
            c.line(x, 300, x, 420)
        for y in (300, 340, 380, 420):
            c.line(100, y, 400, y)
        for r, values in enumerate(self.expected):
            for col, value in enumerate(values):
                c.drawString(110 + 150 * col, 400 - 40 * r, value)
        c.restoreState(); c.drawString(300, 10, '1'); c.save()
        original = source.read_bytes()
        self.assertEqual(PdfReader(source).pages[0].rotation, 0)
        output = self.root / 'existing.xlsx'; output.write_bytes(b'previous workbook')
        for models in ({}, {'PDF_EXCEL_MODELS': '/unused-models'}):
            with patch.dict(os.environ, models, clear=True), patch(
                'convert.extract_layout_tables', side_effect=AssertionError('model must not run')
            ):
                with self.assertRaisesRegex(ConversionError, 'predominantly sideways'):
                    convert(source, output, {})
            self.assertEqual(output.read_bytes(), b'previous workbook')
            self.assertEqual(source.read_bytes(), original)

    def test_unhandled_metadata_rotation_keeps_existing_stirling_route(self):
        source = self.source(90, image=True)
        with patch.dict(os.environ, {"STIRLING_URL": "https://example.invalid"}, clear=True), patch(
            "convert.stirling_tables", side_effect=ConversionError("verified fallback reached")
        ) as fallback:
            with self.assertRaisesRegex(ConversionError, "verified fallback reached"):
                convert(source, self.root / "out.xlsx", {})
        fallback.assert_called_once()

    def test_all_quarter_turns_preserve_literal_cells_without_stirling(self):
        for angle in (90, 180, 270):
            for crop in (False, True):
                with self.subTest(angle=angle, crop=crop):
                    source = self.source(angle, crop=crop)
                    before = hashlib.sha256(source.read_bytes()).hexdigest()
                    output = self.root / "out.xlsx"
                    with patch.dict(os.environ, {}, clear=True):
                        result = convert(source, output, {})
                    book = load_workbook(output)
                    try:
                        self.assertEqual(list(book.active.values), self.expected)
                        self.assertTrue(
                            all(c.data_type == "s" for row in book.active for c in row)
                        )
                    finally:
                        book.close()
                    self.assertTrue(
                        any("oriented upright" in w for w in result["warnings"])
                    )
                    self.assertEqual(
                        hashlib.sha256(source.read_bytes()).hexdigest(), before
                    )
                    self.assertEqual(list(self.root.glob(".pdf-excel-rotation-*")), [])

    def test_normalized_crop_pixels_equal_source_rendered_upright(self):
        import pypdfium2 as pdfium
        from PIL import ImageChops

        for angle in (90, 180, 270):
            for crop in (False, True):
                source = self.source(angle, crop=crop)
                with (
                    prepared_rotation(source, [0], self.root) as (path, _pages),
                    pdfium.PdfDocument(source) as original,
                    pdfium.PdfDocument(path) as normalized,
                ):
                    before = (
                        original[0]
                        .render(scale=2, rotation=(360 - angle) % 360)
                        .to_pil()
                    )
                    after = normalized[0].render(scale=2).to_pil()
                    self.assertEqual(before.size, after.size)
                    self.assertIsNone(ImageChops.difference(before, after).getbbox())

    def test_content_stream_quarter_turns_preserve_cells_and_pixels(self):
        import pypdfium2 as pdfium
        from PIL import ImageChops

        for content_rotation in (90, 180, 270):
            for crop in (False, True):
                source = self.source(content_rotation, crop=crop)
                writer = PdfWriter(clone_from=source)
                writer.pages[0].transfer_rotation_to_content()
                writer.pages[0].rotation = 180
                encoded = self.root / "encoded.pdf"
                writer.write(encoded)
                with (
                    prepared_rotation(encoded, [0], self.root) as (normalized, pages),
                    pdfium.PdfDocument(encoded) as original,
                    pdfium.PdfDocument(normalized) as upright,
                ):
                    self.assertEqual(pages, [1])
                    before = (
                        original[0]
                        .render(scale=2, rotation=(180 - content_rotation) % 360)
                        .to_pil()
                    )
                    after = upright[0].render(scale=2).to_pil()
                    self.assertEqual(before.size, after.size)
                    self.assertIsNone(ImageChops.difference(before, after).getbbox())
                output = self.root / "encoded.xlsx"
                with patch.dict(os.environ, {}, clear=True):
                    convert(encoded, output, {})
                book = load_workbook(output)
                try:
                    self.assertEqual(list(book.active.values), self.expected)
                finally:
                    book.close()

    def test_unrotated_source_is_unchanged(self):
        source = self.source(0)
        with prepared_rotation(source, [0], self.root) as (path, pages):
            self.assertEqual(path, source)
            self.assertEqual(pages, [])

    def test_mixed_direction_or_image_pages_are_not_normalized(self):
        for options in ({"mixed": True}, {"image": True}):
            source = self.source(90, **options)
            with prepared_rotation(source, [0], self.root) as (path, pages):
                self.assertEqual(path, source)
                self.assertEqual(pages, [])

    def test_mixed_rotation_still_refuses_without_conversion_server(self):
        source = self.source(90, mixed=True)
        output = self.root / "mixed.xlsx"
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(ConversionError, "Rotated tables need"),
        ):
            convert(source, output, {})
        self.assertFalse(output.exists())

    def test_unselected_rotation_is_not_changed(self):
        source = self.source(90)
        writer = PdfWriter(clone_from=source)
        writer.add_page(PdfReader(source).pages[0])
        writer.pages[1].rotation = 270
        path = self.root / "two.pdf"
        writer.write(path)
        with prepared_rotation(path, [0], self.root) as (normalized, pages):
            self.assertEqual(pages, [1])
            self.assertEqual(
                [p.rotation for p in PdfReader(normalized).pages], [0, 270]
            )

    def test_oversized_rotated_page_is_not_parsed_before_dimension_rejection(self):
        source = self.source(90)
        writer = PdfWriter(clone_from=source)
        writer.pages[0].mediabox = RectangleObject((0, 0, 20000, 20000))
        writer.pages[0].cropbox = writer.pages[0].mediabox
        path = self.root / "huge.pdf"
        writer.write(path)
        with (
            patch(
                "source_rotation.visible_chars",
                side_effect=AssertionError("must not read glyphs"),
            ),
            prepared_rotation(path, [0], self.root) as (normalized, pages),
        ):
            self.assertEqual(normalized, path)
            self.assertEqual(pages, [])

    def test_temporary_copy_is_removed_after_error(self):
        source = self.source(90)
        with (
            self.assertRaisesRegex(RuntimeError, "failed"),
            prepared_rotation(source, [0], self.root) as (path, _pages),
        ):
            self.assertNotEqual(path, source)
            raise RuntimeError("failed")
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
