import io, sys, unittest
from pathlib import Path
from unittest.mock import patch
import pdfplumber
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
import layout_tables as layout


def document():
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=(240, 240))
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.8, 0.8, 0.8)
    c.rect(10, 20, 90, 100, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.rect(10, 120, 90, 1, stroke=0, fill=1)
    c.rect(120, 20, 90, 100, stroke=1, fill=0)
    c.drawString(20, 80, "12345")
    c.drawString(140, 80, "alpha beta")
    c.showPage()
    c.drawString(30, 180, "Other page")
    c.save()
    b.seek(0)
    return pdfplumber.open(b)


class PhysicalCacheTests(unittest.TestCase):
    def test_repeated_filter_reuses_same_page_and_keeps_rules(self):
        with document() as doc:
            p = doc.pages[0]
            original = list(p.rects)
            with patch.object(
                layout,
                "without_overprinted_blanks",
                wraps=layout.without_overprinted_blanks,
            ) as clean:
                a = layout.physical_page(p)
                b = layout.physical_page(p)
                c = layout.physical_page(a)
                self.assertIs(a, b)
                self.assertIs(c, a)
                self.assertEqual(clean.call_count, 1)
            self.assertEqual(len(p.rects), len(original))
            self.assertEqual(len(a.rects), 2)
            self.assertEqual("".join(c["text"] for c in a.chars), "12345alpha beta")

    def test_crop_does_not_reuse_uncropped_objects(self):
        with document() as doc:
            p = doc.pages[0]
            whole = layout.physical_page(p)
            crop = p.crop((0, 0, 110, 240))
            part = layout.physical_page(crop)
            self.assertIsNot(whole, part)
            self.assertTrue(all(c["x1"] <= 110 for c in part.chars))
            self.assertEqual("".join(c["text"] for c in part.chars), "12345")

    def test_different_pages_and_documents_are_isolated(self):
        with document() as one, document() as two:
            a = layout.physical_page(one.pages[0])
            b = layout.physical_page(one.pages[1])
            c = layout.physical_page(two.pages[0])
            self.assertIsNot(a, b)
            self.assertIsNot(a, c)
            self.assertEqual("".join(ch["text"] for ch in b.chars), "Other page")

    def test_derived_filter_is_rechecked(self):
        with document() as doc:
            p = layout.physical_page(doc.pages[0])
            derived = p.filter(lambda o: o.get("object_type") != "rect")
            result = layout.physical_page(derived)
            self.assertIsNot(result, p)
            self.assertEqual(result.rects, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
