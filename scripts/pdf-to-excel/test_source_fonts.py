import io, tempfile, unittest, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from pypdf import PdfWriter, PdfReader
from pypdf.generic import (
    DictionaryObject as D,
    NameObject as N,
    NumberObject as I,
    ArrayObject as A,
    DecodedStreamObject,
)
from pdfminer.pdffont import CFFFont
import pypdfium2 as pdfium
from source_fonts import repair, font_repairs


def cff_index(items):
    if not items:
        return b"\x00\x00"
    offsets = [1]
    for item in items:
        offsets.append(offsets[-1] + len(item))
    return (
        len(items).to_bytes(2, "big")
        + b"\x02"
        + b"".join(v.to_bytes(2, "big") for v in offsets)
        + b"".join(items)
    )


def integer(n):
    if -107 <= n <= 107:
        return bytes([n + 139])
    return b"\x1c" + n.to_bytes(2, "big", signed=True)


def synthetic_cff():
    names = ["T", "t", "A", "f_i"]
    sids = [
        (
            CFFFont.STANDARD_STRINGS.index(n)
            if n != "f_i"
            else len(CFFFont.STANDARD_STRINGS)
        )
        for n in names
    ]
    # A visible capital T outline, distinct from its lowercase extraction value.
    shape = (
        b"".join(integer(n) for n in [500, 20, 600])
        + b"\x15"
        + b"".join(
            integer(n)
            for n in [400, 0, 0, -80, -160, 0, 0, -520, -80, 0, 0, 520, -160, 0, 0, 80]
        )
        + b"\x05\x0e"
    )
    prefix = b"\x01\x00\x04\x04" + cff_index([b"SyntheticGlyphFont"])
    strings = cff_index([b"f_i"]) + cff_index([])
    charset = b"\x00" + b"".join(s.to_bytes(2, "big") for s in sids)
    encoding = bytes([0, len(names), 84, 116, 65, 30])
    chars = cff_index([b"\x0e"] + [shape] * len(names))
    top = b""
    for _ in range(10):
        start = len(prefix) + len(cff_index([top])) + len(strings)
        new = (
            integer(start)
            + b"\x0f"
            + integer(start + len(charset))
            + b"\x10"
            + integer(start + len(charset) + len(encoding))
            + b"\x11"
        )
        if new == top:
            break
        top = new
    return prefix + cff_index([top]) + strings + charset + encoding + chars


def stream(data):
    s = DecodedStreamObject()
    s.set_data(data)
    return s


def font(mapped="t", embedded=True, encoding="/WinAnsiEncoding"):
    f = D(
        {
            N("/Type"): N("/Font"),
            N("/Subtype"): N("/Type1"),
            N("/BaseFont"): N("/SyntheticGlyphFont"),
            N("/FirstChar"): I(30),
            N("/LastChar"): I(116),
            N("/Widths"): A([I(500)] * 87),
            N("/Encoding"): D(
                {
                    N("/BaseEncoding"): N(encoding),
                    N("/Differences"): A([I(30), N("/f_i")]),
                }
            ),
        }
    )
    desc = D(
        {
            N("/Type"): N("/FontDescriptor"),
            N("/FontName"): N("/SyntheticGlyphFont"),
            N("/Flags"): I(4),
            N("/FontBBox"): A([I(0), I(0), I(500), I(700)]),
            N("/ItalicAngle"): I(0),
            N("/Ascent"): I(700),
            N("/Descent"): I(0),
            N("/CapHeight"): I(600),
            N("/StemV"): I(80),
        }
    )
    if embedded:
        data = stream(synthetic_cff())
        data[N("/Subtype")] = N("/Type1C")
        desc[N("/FontFile3")] = data
    f[N("/FontDescriptor")] = desc
    data = f'/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapType 2 def /CMapName /Synthetic def 1 begincodespacerange <00> <FF> endcodespacerange 4 beginbfchar <54> <{mapped.encode("utf-16-be").hex()}> <74> <0074> <41> <0041> <1E> <0069> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end'.encode()
    f[N("/ToUnicode")] = stream(data)
    return f


def register_font(writer, f):
    descriptor = f["/FontDescriptor"]
    if "/FontFile3" in descriptor:
        descriptor[N("/FontFile3")] = writer._add_object(descriptor["/FontFile3"])
    f[N("/FontDescriptor")] = writer._add_object(descriptor)
    f[N("/ToUnicode")] = writer._add_object(f["/ToUnicode"])
    return writer._add_object(f)


class FontEncodingTests(unittest.TestCase):
    def test_case_and_ligature_have_embedded_glyph_evidence(self):
        result = font_repairs(font())
        self.assertEqual(
            {k: v["after"] for k, v in result[1].items()}, {84: "T", 30: "fi"}
        )

    def test_different_letters_are_not_guessed(self):
        result = font_repairs(font(mapped="Z"))
        self.assertNotIn(84, result[1])
        self.assertIn(b"<54> <005A>", result[0])

    def test_unembedded_or_non_winansi_font_is_unchanged(self):
        self.assertIsNone(font_repairs(font(embedded=False)))
        self.assertIsNone(font_repairs(font(encoding="/SymbolEncoding")))

    def test_no_repair_for_already_correct_capital(self):
        result = font_repairs(font(mapped="T"))
        self.assertNotIn(84, result[1])

    def test_missing_named_glyph_does_not_repair(self):
        f = font()
        f["/Encoding"][N("/Differences")] = A(
            [I(30), N("/unknown"), I(84), N("/Unknown")]
        )
        self.assertIsNone(font_repairs(f))

    def test_real_pdf_changes_only_extraction_and_keeps_pixels_and_original(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / "source.pdf"
            b = Path(temp) / "fixed.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=200, height=200)
            page[N("/Resources")] = D(
                {N("/Font"): D({N("/F1"): register_font(writer, font())})}
            )
            page[N("/Contents")] = writer._add_object(
                stream(b"BT /F1 40 Tf 30 80 Td <5474411E> Tj ET")
            )
            writer.write(a)
            before = a.read_bytes()
            changes = repair(a, b)
            self.assertTrue(changes)
            self.assertEqual(a.read_bytes(), before)
            pixels = []
            texts = []
            for source in [a, b]:
                doc = pdfium.PdfDocument(source)
                p = doc[0]
                bitmap = p.render(scale=2)
                pixels.append(bitmap.to_pil().tobytes())
                text = p.get_textpage()
                texts.append(text.get_text_range())
                text.close()
                bitmap.close()
                p.close()
                doc.close()
            self.assertEqual(pixels[0], pixels[1])
            self.assertEqual(texts, ["ttAi", "TtAfi"])
            self.assertEqual(repair(b, Path(temp) / "again.pdf"), [])
            self.assertFalse((Path(temp) / "again.pdf").exists())

    def test_cid_font_is_untouched(self):
        f = font()
        f[N("/Subtype")] = N("/Type0")
        self.assertIsNone(font_repairs(f))

    def test_resource_forms_are_visited_once(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / "source.pdf"
            b = Path(temp) / "fixed.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=200, height=200)
            f = register_font(writer, font())
            resources = D({N("/Font"): D({N("/F1"): f, N("/F2"): f})})
            x = stream(b"BT /F1 10 Tf 10 10 Td (T) Tj ET")
            x[N("/Subtype")] = N("/Form")
            x[N("/BBox")] = A([I(0), I(0), I(100), I(100)])
            x[N("/Resources")] = resources
            page[N("/Resources")] = D(
                {N("/XObject"): D({N("/X"): writer._add_object(x)})}
            )
            page[N("/Contents")] = writer._add_object(stream(b"/X Do"))
            writer.write(a)
            result = repair(a, b)
            self.assertGreaterEqual(len(result), 1)
            self.assertEqual(
                PdfReader(b)
                .pages[0]["/Resources"]["/XObject"]["/X"]["/Resources"]["/Font"]["/F1"][
                    "/ToUnicode"
                ]
                .get_data()
                .count(b"<54> <0054>"),
                1,
            )

    def test_prepared_source_is_temporary_and_original_survives(self):
        from source_fonts import prepared_source

        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / "source.pdf"
            w = PdfWriter()
            p = w.add_blank_page(width=200, height=200)
            p[N("/Resources")] = D(
                {N("/Font"): D({N("/F1"): register_font(w, font())})}
            )
            w.write(a)
            original = a.read_bytes()
            with prepared_source(a, PdfReader(a), Path(temp)) as changed:
                self.assertNotEqual(changed, a)
                self.assertTrue(changed.exists())
                saved = changed
            self.assertFalse(saved.exists())
            self.assertEqual(a.read_bytes(), original)

    def test_prepared_source_does_not_swallow_conversion_errors(self):
        from source_fonts import prepared_source

        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / "source.pdf"
            w = PdfWriter()
            w.add_blank_page(width=100, height=100)
            w.write(a)
            with self.assertRaisesRegex(RuntimeError, "later conversion failed"):
                with prepared_source(a, PdfReader(a), Path(temp)) as chosen:
                    self.assertEqual(chosen, a)
                    raise RuntimeError("later conversion failed")

    def test_oversized_unicode_map_is_untouched(self):
        f = font()
        f[N("/ToUnicode")] = stream(b" " * 65537)
        self.assertIsNone(font_repairs(f))

    def test_malformed_embedded_font_is_skipped_without_changing_input(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / "source.pdf"
            b = Path(temp) / "fixed.pdf"
            w = PdfWriter()
            p = w.add_blank_page(width=100, height=100)
            f = font()
            f["/FontDescriptor"]["/FontFile3"].set_data(b"broken")
            p[N("/Resources")] = D({N("/Font"): D({N("/F1"): register_font(w, f)})})
            w.write(a)
            before = a.read_bytes()
            self.assertEqual(repair(a, b), [])
            self.assertEqual(a.read_bytes(), before)
            self.assertFalse(b.exists())

    def test_metadata_repair_reaches_actual_workbook_and_cleans_job_scratch(self):
        import os
        from unittest.mock import patch
        from openpyxl import load_workbook
        from convert import convert

        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {}, clear=True
        ):
            root = Path(folder)
            source = root / "source.pdf"
            out = root / "result.xlsx"
            writer = PdfWriter()
            page = writer.add_blank_page(width=300, height=300)
            page[N("/Resources")] = D(
                {N("/Font"): D({N("/F1"): register_font(writer, font())})}
            )
            commands = b"20 100 m 280 100 l 280 220 l 20 220 l h S 20 160 m 280 160 l S 150 100 m 150 220 l S "
            for x, y, text in [
                (30, 190, b"54"),
                (160, 190, b"1E"),
                (30, 130, b"74"),
                (160, 130, b"41"),
            ]:
                commands += f"BT /F1 12 Tf {x} {y} Td <".encode() + text + b"> Tj ET "
            page[N("/Contents")] = writer._add_object(stream(commands))
            writer.write(source)
            before = source.read_bytes()
            convert(source, out, {})
            book = load_workbook(out)
            try:
                self.assertEqual(list(book.active.values), [("T", "fi"), ("t", "A")])
            finally:
                book.close()
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(list(root.glob(".pdf-excel-fonts-*")), [])

    def test_bounded_unicode_ranges_and_arrays_preserve_exact_values(self):
        from source_fonts import single_byte_map

        pre = b"1 begincodespacerange <00> <FF> endcodespacerange "
        self.assertEqual(
            single_byte_map(
                pre
                + b"2 beginbfrange <41> <43> <0041> <54> <55> [<0074> <0055>] endbfrange"
            ),
            {65: "A", 66: "B", 67: "C", 84: "t", 85: "U"},
        )

    def test_multibyte_and_duplicate_unicode_maps_are_not_repaired(self):
        from source_fonts import single_byte_map

        self.assertIsNone(
            single_byte_map(
                b"1 begincodespacerange <00000000> <FFFFFFFF> endcodespacerange 1 beginbfrange <00000000> <FFFFFFFF> <0041> endbfrange"
            )
        )
        self.assertIsNone(
            single_byte_map(
                b"1 begincodespacerange <00> <FF> endcodespacerange 2 beginbfchar <54> <0054> <54> <0074> endbfchar"
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
