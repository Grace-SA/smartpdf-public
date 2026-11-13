import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest

import pdfplumber
from openpyxl import load_workbook
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DecodedStreamObject
from reportlab.pdfgen.canvas import Canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from convert import ruled_tables, write_workbook
from source_bidi import recover, reorder_value


def fixture():
    # Synthetic semantic CMap over standard glyphs exercises PDFium's bidi
    # reading order without bundling a proprietary or downloaded font. This
    # fixture is not a test of Arabic glyph shaping or visual font fidelity.
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(400, 200))
    canvas.setFont("Helvetica", 12)
    letters = list(dict.fromkeys("اسمجديدقسمخاص"))
    encoded = {v: chr(65 + i) for i, v in enumerate(letters)}
    for x in [20, 240, 380]:
        canvas.line(x, 50, x, 150)
    for y in [50, 100, 150]:
        canvas.line(20, y, 380, y)
    for phrase, y in [("اسم جديد", 125), ("قسم خاص", 75)]:
        x = 210
        for word in phrase.split():
            canvas.drawRightString(x, y, "".join(encoded[v] for v in word[::-1]))
            x -= 75
    for value, y in [("12", 125), ("34", 75)]:
        canvas.drawString(280, y, value)
    canvas.save()
    stream.seek(0)
    writer = PdfWriter()
    writer.append_pages_from_reader(PdfReader(stream))
    mapping = {ord(v): k for k, v in encoded.items()}
    entries = [
        f'<{i:02X}> <{mapping.get(i,chr(i)).encode("utf-16-be").hex().upper()}>'
        for i in range(32, 127)
    ]
    cmap = DecodedStreamObject()
    cmap.set_data(
        (
            "/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /SyntheticBidi def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 95 beginbfchar\n"
            + "\n".join(entries)
            + "\nendbfchar endcmap CMapName currentdict /CMap defineresource pop end end"
        ).encode()
    )
    writer.pages[0]["/Resources"]["/Font"]["/F1"][NameObject("/ToUnicode")] = (
        writer._add_object(cmap)
    )
    payload = io.BytesIO()
    writer.write(payload)
    payload.seek(0)
    document = pdfplumber.open(payload)
    page = document.pages[0]
    table = copy.deepcopy(ruled_tables(page)[0])
    by = {(c["r"], c["c"]): c for c in table["cells"]}
    by[0, 0]["text"] = "جديد اسم"
    by[1, 0]["text"] = "خاص قسم"
    return document, page, table


class BidiOrderTests(unittest.TestCase):
    def test_actual_pdf_cell_geometry_restores_reading_order_and_preserves_numbers(
        self,
    ):
        document, page, table = fixture()
        with document:
            before = copy.deepcopy(table)
            position = page.pdf.stream.tell()
            got = recover(table, page, ruled_tables)
            self.assertEqual(table, before)
            self.assertEqual(page.pdf.stream.tell(), position)
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / "result.xlsx"
                write_workbook([dict(got, page=1, index=1)], target, "tables")
                book = load_workbook(target)
                self.assertEqual(
                    list(book.active.values), [("اسم جديد", "12"), ("قسم خاص", "34")]
                )
                book.close()

    def test_cropped_page_uses_original_coordinate_height(self):
        document, page, table = fixture()
        with document:
            cropped = page.crop((0, 20, 400, 170))
            got = recover(table, cropped, ruled_tables)
            self.assertEqual(
                next(c["text"] for c in got["cells"] if (c["r"], c["c"]) == (0, 0)),
                "اسم جديد",
            )

    def test_changed_words_numbers_signs_punctuation_or_multiplicity_are_rejected(self):
        for before, after in [
            ("باب اسم", "اسم ببا"),
            ("12 اسم", "اسم 21"),
            ("012 اسم", "اسم 12"),
            ("-12 اسم", "اسم 12"),
            ("اسم؟ جديد", "جديد اسم"),
            ("اسم اسم جديد", "جديد اسم"),
        ]:
            with self.subTest(before=before, after=after):
                self.assertEqual(reorder_value(before, after), before)

    def test_mixed_latin_name_and_number_keep_exact_tokens(self):
        self.assertEqual(
            reorder_value("1234 Smith John اسم", "اسم John Smith 1234"),
            "اسم John Smith 1234",
        )
        self.assertEqual(reorder_value("שני ראשון", "ראשון שני"), "ראשון שני")

    def test_ltr_single_word_and_multiline_sources_abstain(self):
        for before, after in [
            ("John Smith", "Smith John"),
            ("اسم", "اسم"),
            ("جديد اسم", "اسم\nجديد"),
        ]:
            self.assertEqual(reorder_value(before, after), before)

    def test_ambiguous_or_incomplete_source_grids_never_choose_an_order(self):
        for kind in [
            "ambiguous",
            "missing",
            "overlap",
            "dimension",
            "geometry",
            "nonfinite",
        ]:
            document, page, table = fixture()
            with document:
                native = ruled_tables(page)[0]
                options = [native]
                if kind == "ambiguous":
                    options.append(copy.deepcopy(native))
                elif kind == "missing":
                    native["cells"].pop()
                elif kind == "overlap":
                    native["cells"].append(copy.deepcopy(native["cells"][0]))
                elif kind == "dimension":
                    native["widths"].append(1)
                elif kind == "geometry":
                    native["heights"][0] += 10
                else:
                    native["widths"][0] = float("nan")
                self.assertIs(recover(table, page, lambda _: options), table)

    def test_changed_source_cell_assignment_is_not_repaired_as_reading_order(self):
        document, page, table = fixture()
        with document:
            table["cells"][1]["text"] = "21"
            self.assertIs(recover(table, page, ruled_tables), table)
