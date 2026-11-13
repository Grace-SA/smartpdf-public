"""Native upright pages encoded using /Rotate do not require lossy OCR."""

import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from docx import Document
from PIL import ImageChops
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import NameObject, NumberObject, RectangleObject, DictionaryObject, ArrayObject, NullObject
import pypdfium2 as pdf

from model import Rejected
from test_worker import fixture
from worker import convert, normalize_page_rotations


def upright_rotated(source, root, rotation, *, crop=False, table=False, content=None):
    original = root / "base.pdf"
    commands = b"BT /F1 12 Tf 48 750 Td (Editable 123.45) Tj ET"
    if table:
        commands = b""
        for y in (600, 630, 660):
            commands += f"48 {y} m 300 {y} l S ".encode()
        for x in (48, 170, 300):
            commands += f"{x} 600 m {x} 660 l S ".encode()
        for x, y, text in ((55, 640, "Item"), (180, 640, "Amount"), (55, 610, "A"), (180, 610, "-56.78")):
            commands += f"BT /F1 12 Tf {x} {y} Td ({text}) Tj ET ".encode()
    if content is not None:
        commands = content
    fixture(original, content=commands, crop=crop)
    writer = PdfWriter()
    page = writer.add_page(PdfReader(original).pages[0])
    dx, dy = {0: (0, 0), 90: (792, 0), 180: (612, 792), 270: (0, 612)}[rotation]
    transform = Transformation().rotate(rotation).translate(dx, dy)
    page.add_transformation(transform)
    for key in ("/MediaBox", "/CropBox"):
        if key in page:
            box = RectangleObject(page[key])
            points = [transform.apply_on(point) for point in (box.lower_left, box.upper_right)]
            page[NameObject(key)] = RectangleObject([
                min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points),
            ])
    page[NameObject("/Rotate")] = NumberObject(rotation)
    writer.write(source)


def raster(source):
    with pdf.PdfDocument(source) as document, closing(document[0]) as page:
        with closing(page.render(scale=1.5)) as bitmap:
            return bitmap.to_pil().convert("RGB").copy()


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_upright_rotated_native_text_and_crop_without_ocr(self):
        for rotation in (90, 180, 270):
            for crop in (False, True):
                with self.subTest(rotation=rotation, crop=crop):
                    source = self.root / f"native-{rotation}-{crop}.pdf"
                    output = source.with_suffix(".docx")
                    upright_rotated(source, self.root, rotation, crop=crop)
                    before = source.read_bytes()
                    with patch("worker.OCR.recognize", side_effect=AssertionError("upright native text must not need OCR")):
                        report = convert(source, output)
                    doc = Document(output)
                    self.assertEqual([p.text for p in doc.paragraphs], ["Editable 123.45"])
                    self.assertAlmostEqual(doc.sections[0].page_width.pt, 580 if crop else 612, places=1)
                    self.assertAlmostEqual(doc.sections[0].page_height.pt, 750 if crop else 792, places=1)
                    self.assertEqual(report["warnings"], [])
                    self.assertEqual(source.read_bytes(), before)

    def test_normalization_preserves_rendered_pixels(self):
        for rotation in (90, 180, 270):
            for crop in (False, True):
                with self.subTest(rotation=rotation, crop=crop):
                    source = self.root / f"pixels-{rotation}-{crop}.pdf"
                    upright_rotated(source, self.root, rotation, crop=crop)
                    normalized = normalize_page_rotations(source, self.root)
                    before, after = raster(source), raster(normalized)
                    self.assertEqual(before.size, after.size)
                    self.assertIsNone(ImageChops.difference(before, after).getbbox())

    def test_rotated_native_table_remains_editable(self):
        source, output = self.root / "table.pdf", self.root / "table.docx"
        upright_rotated(source, self.root, 90, table=True)
        with patch("worker.OCR.recognize", side_effect=AssertionError("native table must not need OCR")):
            report = convert(source, output)
        self.assertEqual(report["tables"], 1)
        doc = Document(output)
        self.assertEqual([[c.text for c in r.cells] for r in doc.tables[0].rows], [["Item", "Amount"], ["A", "-56.78"]])
        doc.tables[0].cell(1, 1).text = "99.00"
        doc.save(output)
        self.assertEqual(Document(output).tables[0].cell(1, 1).text, "99.00")

    def test_sideways_text_still_uses_ocr(self):
        source, output = self.root / "sideways.pdf", self.root / "sideways.docx"
        fixture(source, rotation=90)
        with patch("worker.OCR.recognize", side_effect=Rejected("OCR required")) as recognize:
            with self.assertRaisesRegex(Rejected, "OCR required"):
                convert(source, output)
        recognize.assert_called_once()
        self.assertFalse(output.exists())

    def test_encryption_is_rejected_before_normalizing(self):
        source, output = self.root / "encrypted.pdf", self.root / "encrypted.docx"
        fixture(source, rotation=90, protected=True)
        with patch("worker.normalize_page_rotations", side_effect=AssertionError("preflight must run first")):
            with self.assertRaisesRegex(Rejected, "Unlock"):
                convert(source, output)

    def test_hidden_and_clipped_text_still_requires_ocr(self):
        for label, content in (
            ("hidden", b"BT /F1 12 Tf 3 Tr 48 750 Td (Invisible 123) Tj ET"),
            ("clipped", b"BT /F1 12 Tf -15 750 Td (Cut off 123) Tj ET"),
        ):
            with self.subTest(label=label):
                source, output = self.root / f"{label}.pdf", self.root / f"{label}.docx"
                upright_rotated(source, self.root, 90, content=content)
                with patch("worker.OCR.recognize", side_effect=Rejected("OCR required")) as recognize:
                    with self.assertRaisesRegex(Rejected, "OCR required"):
                        convert(source, output)
                recognize.assert_called_once()
                self.assertFalse(output.exists())

    def test_mixed_page_orientations_preserve_page_order(self):
        sources = []
        for rotation in (0, 90, 180, 270):
            source = self.root / f"page-{rotation}.pdf"
            upright_rotated(source, self.root, rotation)
            sources.append(source)
        writer = PdfWriter()
        for source in sources:
            writer.append(source)
        source, output = self.root / "mixed.pdf", self.root / "mixed.docx"
        writer.write(source)
        with patch("worker.OCR.recognize", side_effect=AssertionError("mixed upright native pages must not need OCR")):
            report = convert(source, output)
        self.assertEqual(report["pages"], 4)
        doc = Document(output)
        self.assertEqual(sum(p.text == "Editable 123.45" for p in doc.paragraphs), 4)
        self.assertEqual(doc._element.xml.count('w:name="smartpdf_page_'), 4)

    def test_cancelled_normalization_stops_before_output(self):
        source = self.root / "cancelled.pdf"
        upright_rotated(source, self.root, 90)
        cancel = self.root / "cancel"
        cancel.touch()
        with self.assertRaisesRegex(Rejected, "cancelled"):
            normalize_page_rotations(source, self.root, cancel)
        self.assertEqual(list(self.root.glob("rotation-*.pdf")), [])

    def test_normal_pages_are_not_rewritten(self):
        source = self.root / "normal.pdf"
        fixture(source)
        self.assertEqual(normalize_page_rotations(source, self.root), source)
        self.assertEqual(list(self.root.glob("rotation-*.pdf")), [])

    def test_mixed_document_retains_rotated_blank_null_content_page(self):
        source, output = self.root / "blank-mixed.pdf", self.root / "blank-mixed.docx"
        fixture(source)
        writer = PdfWriter()
        writer.append(source)
        blank = writer.add_blank_page(612, 792)
        blank[NameObject("/Rotate")] = NumberObject(90)
        blank[NameObject("/Contents")] = NullObject()
        writer.write(source)
        with patch("worker.OCR.recognize", side_effect=AssertionError("blank page needs no OCR")):
            report = convert(source, output)
        doc = Document(output)
        self.assertEqual(report["pages"], 2)
        self.assertEqual(len(doc.sections), 2)
        self.assertEqual(sum(p.text == "Editable 123.45" for p in doc.paragraphs), 1)
        self.assertEqual(doc._element.xml.count('w:name="smartpdf_page_'), 2)

    def test_equivalent_rotation_angles_are_canonicalized(self):
        for rotation in (-270, 450, 360000090):
            with self.subTest(rotation=rotation):
                source = self.root / f"equivalent-{rotation}.pdf"
                upright_rotated(source, self.root, 90)
                writer = PdfWriter()
                page = writer.add_page(PdfReader(source).pages[0])
                page[NameObject("/Rotate")] = NumberObject(rotation)
                writer.write(source)
                result = normalize_page_rotations(source, self.root)
                self.assertEqual(raster(source).size, raster(result).size)
                self.assertIsNone(ImageChops.difference(raster(source), raster(result)).getbbox())

    def test_extreme_rotation_is_rejected_before_geometry_changes(self):
        source = self.root / "extreme.pdf"
        fixture(source, rotation=360000000000090)
        with self.assertRaisesRegex(Rejected, "rotation"):
            normalize_page_rotations(source, self.root)
        self.assertEqual(list(self.root.glob("rotation-*.pdf")), [])

    def test_expanded_rotated_instructions_are_bounded(self):
        source = self.root / "large.pdf"
        fixture(source, rotation=90, content=b" " * (8 * 1024**2 + 1))
        with self.assertRaisesRegex(Rejected, "instructions exceed"):
            normalize_page_rotations(source, self.root)
        self.assertEqual(list(self.root.glob("rotation-*.pdf")), [])

    def test_aggregate_rotated_instruction_budget_is_bounded(self):
        from types import SimpleNamespace

        class SizedData:
            def __len__(self):
                return 8 * 1024**2

        class Stream:
            def get_object(self):
                return self

            def get_data(self):
                return SizedData()

        pages = [SimpleNamespace(rotation=90, get=lambda key: Stream() if key == "/Contents" else None) for _ in range(9)]
        with patch("worker.PdfReader", return_value=SimpleNamespace(pages=pages)), patch("worker.PdfWriter"):
            with self.assertRaisesRegex(Rejected, "document instructions exceed"):
                normalize_page_rotations(self.root / "synthetic.pdf", self.root)
        self.assertEqual(list(self.root.glob("rotation-*.pdf")), [])

    def test_annotated_page_is_not_normalized_or_moved(self):
        source = self.root / "annotated.pdf"
        upright_rotated(source, self.root, 90)
        writer = PdfWriter()
        page = writer.add_page(PdfReader(source).pages[0])
        page[NameObject("/Annots")] = ArrayObject([writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): RectangleObject([20, 20, 150, 80]),
            NameObject("/Border"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(2)]),
        }))])
        writer.write(source)
        before = source.read_bytes()
        self.assertEqual(normalize_page_rotations(source, self.root), source)
        self.assertEqual(source.read_bytes(), before)
        other = self.root / "other.pdf"
        upright_rotated(other, self.root, 180)
        writer.append(other)
        mixed = self.root / "annotated-mixed.pdf"
        writer.write(mixed)
        normalized = normalize_page_rotations(mixed, self.root)
        self.assertNotEqual(normalized, mixed)
        self.assertEqual(PdfReader(normalized).pages[0].rotation, 90)
        self.assertEqual(PdfReader(normalized).pages[1].rotation, 0)
        self.assertIsNone(ImageChops.difference(raster(mixed), raster(normalized)).getbbox())


if __name__ == "__main__":
    unittest.main()
