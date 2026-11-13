import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import load_workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import ConversionError, clean, convert, write_workbook


class AtomicWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.output = self.root / "output.xlsx"
        self.tables = [
            dict(
                page=1,
                index=1,
                widths=[80, 80],
                heights=[20, 20],
                cells=[dict(r=0, c=0, rs=1, cs=1, text="00123")],
            )
        ]

    def assert_clean(self):
        self.assertFalse(list(self.root.glob(".pdf-excel-workbook-*")))

    def test_success_publishes_valid_workbook(self):
        write_workbook(self.tables, self.output, "tables")
        book = load_workbook(self.output)
        self.assertEqual(book.active["A1"].value, "00123")
        book.close()
        self.assert_clean()

    def test_failed_serialization_never_publishes_or_replaces_output(self):
        def fail(book, path):
            Path(path).write_bytes(b"PK partial file")
            raise OSError("disk fault")

        for existing in (False, True):
            if existing:
                self.output.write_bytes(b"prior output")
            with (
                patch("convert.Workbook.save", autospec=True, side_effect=fail),
                self.assertRaises(OSError),
            ):
                write_workbook(self.tables, self.output, "tables")
            if existing:
                self.assertEqual(self.output.read_bytes(), b"prior output")
            else:
                self.assertFalse(self.output.exists())
            self.assert_clean()

    def test_oversized_output_does_not_replace_previous_file(self):
        self.output.write_bytes(b"prior output")
        with (
            patch("convert.MAX_BYTES", 20),
            self.assertRaisesRegex(ConversionError, "download size"),
        ):
            write_workbook(self.tables, self.output, "tables")
        self.assertEqual(self.output.read_bytes(), b"prior output")
        self.assert_clean()

    def test_illegal_xml_cell_values_are_explicitly_rejected(self):
        for value in ("bad\ufffe", "bad\uffff", "bad\ud800"):
            with self.assertRaisesRegex(ConversionError, "characters"):
                clean(value)
        self.assertEqual(clean("valid 😀"), "valid 😀")

    def test_real_pdf_invalid_font_mapping_leaves_no_workbook(self):
        source = self.root / "source.pdf"
        c = canvas.Canvas(str(source), pagesize=(400, 400))
        for x in (50, 180, 310):
            c.line(x, 100, x, 250)
        for y in (100, 150, 200, 250):
            c.line(50, y, 310, y)
        for r, values in enumerate(
            (("Name", "Amount"), ("Apple", "123"), ("Pear", "456"))
        ):
            for col, value in enumerate(values):
                c.drawString(60 + col * 130, 230 - r * 50, value)
        c.save()
        writer = PdfWriter(clone_from=source)
        font = writer.pages[0]["/Resources"]["/Font"]["/F1"].get_object()
        cmap = DecodedStreamObject()
        cmap.set_data(
            b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /Test def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 1 beginbfchar <41> <FFFE> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end"
        )
        font[NameObject("/ToUnicode")] = writer._add_object(cmap)
        invalid = self.root / "invalid.pdf"
        writer.write(invalid)
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(ConversionError, "characters"),
        ):
            convert(invalid, self.output, {"ocr": False})
        self.assertFalse(self.output.exists())
        self.assert_clean()

    def test_postvalidation_rejects_external_relationships_atomically(self):
        def inject(path, *_):
            with ZipFile(path) as z:
                members = {name: z.read(name) for name in z.namelist()}
            name = "xl/_rels/workbook.xml.rels"
            tree = ET.fromstring(members[name])
            ET.SubElement(
                tree,
                "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                {
                    "Id": "unsafe",
                    "Type": "externalLink",
                    "Target": "https://example.invalid",
                    "TargetMode": "External",
                },
            )
            members[name] = ET.tostring(tree)
            with ZipFile(path, "w", ZIP_DEFLATED) as z:
                for name, data in members.items():
                    z.writestr(name, data)

        self.output.write_bytes(b"prior output")
        with (
            patch("convert.attach_form_rules", side_effect=inject),
            self.assertRaisesRegex(ConversionError, "external relationship"),
        ):
            write_workbook(self.tables, self.output, "tables")
        self.assertEqual(self.output.read_bytes(), b"prior output")
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
