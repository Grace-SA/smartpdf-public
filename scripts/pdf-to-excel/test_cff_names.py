import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from cff_names import glyph_names, top_dictionary
from test_source_fonts import cff_index, integer, font, stream
from source_fonts import font_repairs, single_byte_map
from pdfminer.pdffont import CFFFont
from pypdf.generic import NameObject as N


def cff(format=0, names=("T", "t", "A", "f_i"), malformed=None, cid=False):
    standard = CFFFont.STANDARD_STRINGS
    custom = [n for n in names if n not in standard]
    sids = [
        standard.index(n) if n in standard else len(standard) + custom.index(n)
        for n in names
    ]
    charset = bytes([format])
    cursor = 0
    while cursor < len(sids):
        first = sids[cursor]
        length = 1
        if format:
            while (
                cursor + length < len(sids) and sids[cursor + length] == first + length
            ):
                length += 1
        charset += first.to_bytes(2, "big")
        if format:
            charset += (length - 1).to_bytes(format, "big")
        cursor += length
    if malformed is not None:
        charset = malformed
    prefix = b"\1\0\4\4" + cff_index([b"SyntheticCharset"])
    strings = cff_index([n.encode("ascii") for n in custom]) + cff_index([])
    programs = cff_index([b"\x0e"] * (len(names) + 1))
    top = b""
    for _ in range(10):
        start = len(prefix) + len(cff_index([top])) + len(strings)
        new = integer(start) + b"\x0f" + integer(start + len(charset)) + b"\x11"
        if cid:
            new += integer(0) + integer(1) + integer(0) + b"\x0c\x1e"
        if new == top:
            break
        top = new
    return prefix + cff_index([top]) + strings + charset + programs


class CffNamesTests(unittest.TestCase):
    def test_simple_font_wide_declaration_requires_actual_one_byte_entries(self):
        f = font()
        raw = f["/ToUnicode"].get_data().replace(b"<00> <FF>", b"<0000> <FFFF>")
        self.assertIsNone(single_byte_map(raw))
        self.assertEqual(single_byte_map(raw, allow_wide_declaration=True)[84], "t")
        f[N("/ToUnicode")] = stream(raw)
        self.assertEqual(font_repairs(f)[1][84]["after"], "T")
        bad = raw.replace(b"<54>", b"<0054>")
        with self.assertRaises(ValueError):
            single_byte_map(bad, allow_wide_declaration=True)
        f[N("/Subtype")] = N("/Type0")
        self.assertIsNone(font_repairs(f))

    def test_all_custom_formats_and_inclusive_ranges(self):
        for format in (0, 1, 2):
            for names in [("T", "t", "A", "f_i"), ("A", "B", "C", "D")]:
                self.assertEqual(glyph_names(cff(format, names)), set(names))

    def test_new_charset_formats_repair_only_verified_case_and_ligature(self):
        for format in (1, 2):
            f = font()
            s = stream(cff(format))
            s[N("/Subtype")] = N("/Type1C")
            f["/FontDescriptor"][N("/FontFile3")] = s
            content, changes = font_repairs(f)
            self.assertEqual(changes[84]["after"], "T")
            self.assertEqual(changes[30]["after"], "fi")
            self.assertEqual(set(changes), {30, 84})

    def test_truncated_indices_and_charsets_are_rejected(self):
        for format in (0, 1, 2):
            data = cff(format)
            for length in range(len(data)):
                self.assertIsNone(glyph_names(data[:length]), (format, length))

    def test_excess_ranges_duplicates_cids_and_version_two_are_rejected(self):
        for data in [
            cff(1, malformed=b"\1\0\x22\xff"),
            cff(2, malformed=b"\2\0\x22\xff\xff"),
            cff(0, names=("A", "A")),
            cff(cid=True),
            b"\2" + cff()[1:],
            cff(0, malformed=b"\x03"),
            b"\1\0\4\4\xff\xff\4",
        ]:
            self.assertIsNone(glyph_names(data))

    def test_escaped_operators_do_not_become_unbounded_operands(self):
        self.assertIn((12, 30), top_dictionary(b"\x8b\x8c\x8b\x0c\x1e"))
        for data in [
            b"\x0c",
            b"\x8b" * 49 + b"\x0f",
            b"\x1e" + b"\x11" * 33,
            b"\xff",
            b"\x8b\x0f\x8c\x0f",
        ]:
            with self.assertRaises((ValueError, IndexError)):
                top_dictionary(data)


if __name__ == "__main__":
    unittest.main()
