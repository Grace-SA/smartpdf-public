"""Original hidden-layer fixtures, entirely generated in memory."""

import base64
import io
import sys
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    EncodedStreamObject,
    NameObject,
    NullObject,
)
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
import source_hidden_ocr as m


def fixture(text=b"BT /F1 12 Tf 3 Tr (19.50) Tj ET", prefix=b"", suffix=b""):
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(300, 200))
    pdf.drawImage(ImageReader(Image.new("RGB", (300, 200), "white")), 0, 0, 300, 200)
    pdf.save()
    reader = PdfReader(io.BytesIO(buf.getvalue()))
    page = reader.pages[0]
    name = next(iter(page["/Resources"]["/XObject"]))
    data = b"q 300 0 0 200 0 0 cm " + str(name).encode() + b" Do Q\n"
    stream = DecodedStreamObject()
    stream.set_data(prefix + data + text + suffix)
    page[NameObject("/Contents")] = stream
    return page


def scanned_table(hidden=True, ruled=True):
    """Visible 12.50 with an optional, contradictory invisible 19.50 layer."""
    import pypdfium2 as pdfium

    rows = (
        ("Code", "Amount"),
        ("123", "12.50"),
        ("007", "18.00"),
        ("321", "25.30"),
        ("555", "10.00"),
    )

    def write_text(pdf, invisible):
        for r, row in enumerate(rows):
            for col, value in enumerate(row):
                text = pdf.beginText(110 + 150 * col, 480 - 40 * r)
                text.setFont("Helvetica", 14)
                if invisible:
                    text.setTextRenderMode(3)
                    if r == 1 and col == 1:
                        value = "19.50"
                text.textOut(value)
                pdf.drawText(text)

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(600, 600))
    if ruled:
        for x in (100, 250, 400):
            pdf.line(x, 300, x, 500)
        for y in range(300, 501, 40):
            pdf.line(100, y, 400, y)
    write_text(pdf, False)
    pdf.save()
    with pdfium.PdfDocument(buf.getvalue()) as document:
        page = document[0]
        bitmap = page.render(scale=2)
        image = bitmap.to_pil().copy()
        bitmap.close()
        page.close()
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(600, 600))
    pdf.drawImage(ImageReader(image), 0, 0, 600, 600)
    if hidden:
        write_text(pdf, True)
    pdf.save()
    return buf.getvalue()


def form_fixture(
    content=b"BT /F1 12 Tf 3 Tr (layer) Tj ET", parent=b"BT /F1 12 Tf 3 Tr ET"
):
    from pypdf.generic import DictionaryObject, NumberObject

    page = fixture(parent)
    form = DecodedStreamObject()
    form.set_data(content)
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/FormType"): NumberObject(1),
            NameObject("/BBox"): ArrayObject(
                [NumberObject(v) for v in (0, 0, 300, 200)]
            ),
            NameObject("/Resources"): DictionaryObject(
                {NameObject("/Font"): page["/Resources"]["/Font"]}
            ),
        }
    )
    page["/Resources"]["/XObject"][NameObject("/OCR")] = form
    stream = page["/Contents"]
    stream.set_data(stream.get_data() + b"\n/OCR Do\n")
    return page, form


class HiddenOCRTests(unittest.TestCase):
    def test_original_scanned_table_has_identical_visible_pixels(self):
        import pypdfium2 as pdfium
        from PIL import ImageChops

        rendered = []
        for hidden in (False, True):
            data = scanned_table(hidden)
            self.assertEqual(
                m.classify(PdfReader(io.BytesIO(data)).pages[0]),
                "hidden" if hidden else "other",
            )
            with pdfium.PdfDocument(data) as document:
                page = document[0]
                bitmap = page.render(scale=2)
                rendered.append(bitmap.to_pil().copy())
                bitmap.close()
                page.close()
        self.assertIsNone(ImageChops.difference(*rendered).getbbox())

    def test_image_mask_and_optional_content_rejected(self):
        from pypdf.generic import DictionaryObject

        for key in ("/SMask", "/SMaskInData", "/Mask", "/ImageMask", "/OC"):
            page = fixture()
            image = next(iter(page["/Resources"]["/XObject"].values())).get_object()
            image[NameObject(key)] = DictionaryObject()
            with self.subTest(key=key):
                self.assertEqual(m.classify(page), "unsupported")

    def test_hidden_text_only_form_and_inherited_state(self):
        for content in (b"BT /F1 12 Tf 3 Tr (hidden) Tj ET", b"BT (inherited) Tj ET"):
            self.assertEqual(m.classify(form_fixture(content)[0]), "hidden")
        self.assertEqual(
            m.classify(form_fixture(b"BT (visible) Tj ET", b"BT /F1 12 Tf ET")[0]),
            "unsupported",
        )

    def test_form_visible_mixed_and_invalid_font(self):
        for content in (
            b"BT /F1 12 Tf 0 Tr (visible) Tj ET",
            b"BT /F1 12 Tf 3 Tr (hidden) Tj 0 Tr (visible) Tj ET",
            b"BT /Missing 12 Tf 3 Tr (hidden) Tj ET",
            b"BT (missing font) Tj ET",
        ):
            self.assertEqual(m.classify(form_fixture(content, b"")[0]), "unsupported")

    def test_form_resource_shadow_does_not_rebind_inherited_font(self):
        from pypdf.generic import DictionaryObject

        page, form = form_fixture(b"BT (inherited) Tj ET")
        form["/Resources"][NameObject("/Font")] = DictionaryObject(
            {
                NameObject("/F1"): DictionaryObject(
                    {NameObject("/Subtype"): NameObject("/Type3")}
                )
            }
        )
        self.assertEqual(m.classify(page), "hidden")
        form.set_data(b"BT /F1 12 Tf 3 Tr (local Type3) Tj ET")
        self.assertEqual(m.classify(page), "unsupported")

    def test_form_state_does_not_leak(self):
        page, form = form_fixture(parent=b"BT /F1 12 Tf 0 Tr ET")
        stream = page["/Contents"]
        stream.set_data(stream.get_data() + b"BT (visible parent) Tj ET")
        self.assertEqual(m.classify(page), "other")
        page, form = form_fixture(
            b"20 0 0 20 100 100 cm BT /F1 12 Tf 3 Tr (hidden) Tj ET", parent=b""
        )
        stream = page["/Contents"]
        stream.set_data(b"/OCR Do\n" + stream.get_data().replace(b"/OCR Do", b""))
        self.assertEqual(m.classify(page), "hidden")
        form.set_data(b"q BT /F1 12 Tf 3 Tr (unbalanced) Tj ET")
        self.assertEqual(m.classify(page), "unsupported")

    def test_form_nested_objects_and_graphics_rejected(self):
        for content in (
            b"/OCR Do",
            b"/Image Do",
            b"0 0 1 1 re f",
            b"/GS0 gs",
            b"/Sh0 sh",
            b"0 0 300 200 re W n",
            b"/OC /Prop BDC EMC",
        ):
            with self.subTest(content=content):
                self.assertEqual(m.classify(form_fixture(content)[0]), "unsupported")

    def test_form_attributes_and_geometry_rejected(self):
        from pypdf.generic import DictionaryObject, FloatObject, NumberObject

        for key in ("/Group", "/OC", "/Ref", "/F", "/SMask", "/DecodeParms"):
            page, form = form_fixture()
            form[NameObject(key)] = DictionaryObject()
            self.assertEqual(m.classify(page), "unsupported")
        for box in ((0, 0, 0, 100), (0, 0, 100), (0, 0, float("nan"), 100)):
            page, form = form_fixture()
            form[NameObject("/BBox")] = ArrayObject([FloatObject(v) for v in box])
            self.assertEqual(m.classify(page), "unsupported")
        page, form = form_fixture()
        form[NameObject("/Matrix")] = ArrayObject(
            [NumberObject(v) for v in (1, 0, 0, 1, 1, 0)]
        )
        self.assertEqual(m.classify(page), "unsupported")
        page, form = form_fixture()
        form[NameObject("/Type")] = NameObject("/Page")
        self.assertEqual(m.classify(page), "unsupported")
        page, form = form_fixture()
        del form["/Resources"]
        self.assertEqual(m.classify(page), "unsupported")

    def test_form_budgets_shared_with_page_and_repeated_calls(self):
        page, form = form_fixture()
        parent_size = len(page["/Contents"].get_data()) + 1
        with patch.object(m, "MAX_BYTES", parent_size + len(form.get_data())):
            self.assertEqual(m.classify(page), "unsupported")
        with patch.object(m, "MAX_STREAMS", 1):
            self.assertEqual(m.classify(page), "unsupported")
        from pypdf.generic import ContentStream

        count = len(ContentStream(page["/Contents"], page.pdf).operations)
        count += len(ContentStream(form, page.pdf).operations)
        with patch.object(m, "MAX_OPS", count - 1):
            self.assertEqual(m.classify(page), "unsupported")
        stream = page["/Contents"]
        stream.set_data(stream.get_data() + b"/OCR Do\n" * m.MAX_FORMS)
        self.assertEqual(m.classify(page), "unsupported")

    def test_simple_hidden_scan(self):
        self.assertEqual(m.classify(fixture()), "hidden")

    def test_hidden_text_before_or_after_image(self):
        hidden = b"BT /F1 12 Tf 3 Tr (hidden) Tj ET "
        for prefix, text in [(hidden, b""), (b"", hidden), (hidden, hidden)]:
            with self.subTest(prefix=bool(prefix), suffix=bool(text)):
                self.assertEqual(
                    m.classify(fixture(text=text, prefix=prefix)), "hidden"
                )
        self.assertEqual(
            m.classify(fixture(text=b"", prefix=b"BT /F1 12 Tf (visible) Tj ET ")),
            "other",
        )

    def test_font_and_ctm_restore_across_graphics_stack(self):
        # Restoring q/Q must discard a font selected only in that scope.
        self.assertEqual(
            m.classify(fixture(b"q BT /F1 12 Tf 3 Tr (x) Tj ET Q BT 3 Tr (x) Tj ET")),
            "unsupported",
        )
        # A temporary translated/scaled CTM cannot affect the later image.
        self.assertEqual(m.classify(fixture(prefix=b"q 2 0 0 2 50 30 cm Q ")), "hidden")
        page = fixture()
        data = page["/Contents"].get_data()
        split = data.index(b" Do")
        first, second = DecodedStreamObject(), DecodedStreamObject()
        first.set_data(data[:split])
        second.set_data(data[split:])
        page[NameObject("/Contents")] = ArrayObject([first, second])
        self.assertEqual(m.classify(page), "hidden")

    def test_all_show_operators(self):
        for show in (b"(x) Tj", b"[(x) 10 (y)] TJ", b"(x) '", b'0 0 (x) "'):
            with self.subTest(show=show):
                self.assertEqual(
                    m.classify(fixture(b"BT /F1 12 Tf 3 Tr " + show + b" ET")), "hidden"
                )

    def test_state_survives_text_objects_and_contents(self):
        page = fixture(b"BT /F1 12 Tf 3 Tr (first) Tj ET")
        second = DecodedStreamObject()
        second.set_data(b"BT (second) Tj ET")
        page[NameObject("/Contents")] = ArrayObject([page["/Contents"], second])
        self.assertEqual(m.classify(page), "hidden")
        second.set_data(b"BT 0 Tr (second) Tj ET")
        self.assertEqual(m.classify(page), "other")

    def test_graphics_stack_restores_text_rendering_state(self):
        good = b"BT /F1 12 Tf 3 Tr ET q BT 0 Tr ET Q BT (hidden) Tj ET"
        bad = b"BT /F1 12 Tf 0 Tr ET q BT 3 Tr (hidden) Tj ET Q BT (visible) Tj ET"
        self.assertEqual(m.classify(fixture(good)), "hidden")
        self.assertEqual(m.classify(fixture(bad)), "other")

    def test_visible_mixed_and_empty_are_other(self):
        for text in (
            b"",
            b"BT /F1 12 Tf 3 Tr () Tj [] TJ ET",
            b"BT /F1 12 Tf (visible) Tj ET",
            b"BT /F1 12 Tf 3 Tr (hidden) Tj 0 Tr (visible) Tj ET",
            b"1 g BT /F1 12 Tf (white) Tj ET",
        ):
            with self.subTest(text=text):
                self.assertEqual(m.classify(fixture(text)), "other")

    def test_clipping_alpha_shading_unknown_rejected(self):
        for prefix in (b"0 0 300 200 re W n ", b"/GS0 gs ", b"/SH0 sh ", b"wat "):
            with self.subTest(prefix=prefix):
                self.assertEqual(m.classify(fixture(prefix=prefix)), "unsupported")
        self.assertEqual(
            m.classify(fixture(b"BT /F1 12 Tf 7 Tr (clip) Tj ET")), "unsupported"
        )

    def test_form_and_type3_rejected(self):
        page = fixture()
        image = next(iter(page["/Resources"]["/XObject"].values())).get_object()
        image[NameObject("/Subtype")] = NameObject("/Form")
        self.assertEqual(m.classify(page), "unsupported")
        page = fixture()
        page["/Resources"]["/Font"]["/F1"][NameObject("/Subtype")] = NameObject(
            "/Type3"
        )
        self.assertEqual(m.classify(page), "unsupported")

    def test_partial_or_multiple_images_not_classified(self):
        page = fixture()
        stream = page["/Contents"]
        stream.set_data(stream.get_data().replace(b"300 0 0 200", b"150 0 0 200"))
        self.assertEqual(m.classify(page), "other")
        page = fixture()
        stream = page["/Contents"]
        stream.set_data(stream.get_data() + b"\n" + stream.get_data())
        self.assertEqual(m.classify(page), "other")

    def test_malformed_streams_and_operands(self):
        for text in (
            b"Q",
            b"q",
            b"BT",
            b"ET",
            b"BT BT ET ET",
            b"BT /F1 12 Tf 3.5 Tr (x) Tj ET",
            b"BT /F1 12 Tf 3 Tr 42 Tj ET",
            b"BT /F1 12 Tf 3 Tr [true] TJ ET",
            b"BT /Unknown 12 Tf (x) Tj ET",
            b"BT /F1 -1 Tf (x) Tj ET",
            b"0 0 cm",
            b"(x) Tj",
        ):
            with self.subTest(text=text):
                self.assertEqual(m.classify(fixture(text)), "unsupported")

    def test_budgets(self):
        with patch.object(m, "MAX_BYTES", 10):
            self.assertEqual(m.classify(fixture()), "unsupported")
        with patch.object(m, "MAX_OPS", 1):
            self.assertEqual(m.classify(fixture()), "unsupported")
        with patch.object(m, "MAX_STACK", 1):
            self.assertEqual(
                m.classify(fixture(prefix=b"q q ", suffix=b"Q Q")), "unsupported"
            )
        page = fixture()
        page[NameObject("/Contents")] = ArrayObject([page["/Contents"]] * 33)
        self.assertEqual(m.classify(page), "unsupported")

    def test_bounded_standard_filters_and_reportlab_content(self):
        for filters in [
            ("/FlateDecode",),
            ("/Fl",),
            ("/ASCII85Decode",),
            ("/A85",),
            ("/ASCII85Decode", "/FlateDecode"),
        ]:
            page = fixture()
            data = page["/Contents"].get_data()
            for name in reversed(filters):
                data = (
                    zlib.compress(data)
                    if name in ("/Fl", "/FlateDecode")
                    else base64.a85encode(data, adobe=True)
                )
            stream = EncodedStreamObject()
            stream._data = data
            stream[NameObject("/Filter")] = ArrayObject(
                [NameObject(f) for f in filters]
            )
            page[NameObject("/Contents")] = stream
            with (
                self.subTest(filters=filters),
                patch.object(
                    EncodedStreamObject,
                    "get_data",
                    side_effect=AssertionError("unbounded decoder called"),
                ),
            ):
                self.assertEqual(m.classify(page), "hidden")
                self.assertIsNone(stream.decoded_self)
        page = PdfReader(io.BytesIO(scanned_table(True))).pages[0]
        self.assertEqual(
            list(page["/Contents"]["/Filter"]), ["/ASCII85Decode", "/FlateDecode"]
        )
        self.assertEqual(m.classify(page), "hidden")

    def test_flate_bomb_trailing_and_truncated_content_rejected_without_cache(self):
        page = fixture()
        ordinary = page["/Contents"].get_data()
        for data in [
            zlib.compress(b" " * (m.MAX_BYTES + 1)),
            zlib.compress(ordinary) + b"trailing",
            zlib.compress(ordinary)[:-1],
        ]:
            stream = EncodedStreamObject()
            stream._data = data
            stream[NameObject("/Filter")] = NameObject("/FlateDecode")
            page[NameObject("/Contents")] = stream
            with patch.object(
                EncodedStreamObject,
                "get_data",
                side_effect=AssertionError("unbounded decoder called"),
            ):
                self.assertEqual(m.classify(page), "unsupported")
                self.assertIsNone(stream.decoded_self)

    def test_unknown_filters_parameters_and_stage_budget(self):
        for filters, params in [
            (["/LZWDecode"], None),
            (["/FlateDecode"] * 3, None),
            (["/FlateDecode"], DictionaryObject()),
            (["/FlateDecode"], NullObject()),
        ]:
            page = fixture()
            stream = EncodedStreamObject()
            stream._data = zlib.compress(page["/Contents"].get_data())
            stream[NameObject("/Filter")] = ArrayObject(
                [NameObject(f) for f in filters]
            )
            if params is not None:
                stream[NameObject("/DecodeParms")] = params
            page[NameObject("/Contents")] = stream
            self.assertEqual(m.classify(page), "unsupported")

    def test_ascii85_expansion_budget_is_checked_before_decode(self):
        page = fixture()
        stream = EncodedStreamObject()
        stream._data = b"z" * 30 + b"~>"
        stream[NameObject("/Filter")] = NameObject("/ASCII85Decode")
        page[NameObject("/Contents")] = stream
        with (
            patch.object(m, "MAX_BYTES", 100),
            patch.object(
                m.base64,
                "a85decode",
                side_effect=AssertionError("overbudget decoder called"),
            ),
        ):
            self.assertEqual(m.classify(page), "unsupported")

    def test_decoded_budget_accumulates_across_streams(self):
        page = fixture()
        original = page["/Contents"]
        padding = DecodedStreamObject()
        padding.set_data(b" " * 50)
        page[NameObject("/Contents")] = ArrayObject([original, padding, padding])
        with patch.object(m, "MAX_BYTES", len(original.get_data()) + 80):
            self.assertEqual(m.classify(page), "unsupported")

    def test_crop_and_rotation(self):
        page = fixture()
        page.cropbox.upper_right = (280, 200)
        self.assertEqual(m.classify(page), "hidden")
        page = fixture()
        page.rotate(90)
        self.assertEqual(m.classify(page), "unsupported")


if __name__ == "__main__":
    unittest.main()
