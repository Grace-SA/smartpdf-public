import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from reportlab.pdfgen import canvas
import pdfplumber
import pypdfium2 as pdf
from invisible_margins import proven_margin_objects, exclude_margin_text
from worker import needs_ocr


class InvisibleMarginTests(unittest.TestCase):
    def test_off_page_white_objects_do_not_disable_native_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'off-page.pdf'
            c=canvas.Canvas(str(source),pagesize=(612,792))
            c.drawString(40,30,'Catalog identifier 12345I remains editable.')
            c.setFillColorRGB(1,1,1)
            c.drawString(720,400,'Off-page content')
            c.save()
            with pdf.PdfDocument(source) as d,pdfplumber.open(source) as pl,closing(d[0]) as page,closing(page.get_textpage()) as tp:
                self.assertEqual(proven_margin_objects(page,tp),[])
                self.assertIs(exclude_margin_text(page,pl.pages[0]),pl.pages[0])

    def fixture(self,path,background=False,body=False):
        c=canvas.Canvas(str(path),pagesize=(612,792));c.setFont('Helvetica',10)
        c.drawString(50,700,'Visible source paragraph remains editable.')
        if background:c.setFillColorRGB(0,0,0);c.rect(0,0,612,36,fill=1,stroke=0)
        c.setFillColorRGB(1,1,1);c.drawString(50,400 if body else 20,'Synthetic printer mark')
        c.save()

    def test_invisible_margin_excluded_with_original_and_visible_text_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf';self.fixture(source);before=source.read_bytes()
            with pdf.PdfDocument(source) as d,pdfplumber.open(source) as pl,closing(d[0]) as page:
                self.assertFalse(needs_ocr(page)[0])
                filtered=exclude_margin_text(page,pl.pages[0]);self.assertIsNotNone(filtered)
                text=''.join(c['text'] for c in filtered.chars)
                self.assertIn('Visible source paragraph remains editable.',text)
                self.assertNotIn('Synthetic printer mark',text)
                with closing(page.get_textpage()) as tp:
                    # In-memory proof restores drawing modes and source text.
                    self.assertIn('Synthetic printer mark',tp.get_text_range())
            self.assertEqual(source.read_bytes(),before)

    def test_visible_white_text_and_body_text_are_not_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ('contrast','body'):
                source=Path(tmp)/(mode+'.pdf');self.fixture(source,background=mode=='contrast',body=mode=='body')
                with pdf.PdfDocument(source) as d,pdfplumber.open(source) as pl,closing(d[0]) as page,closing(page.get_textpage()) as tp:
                    self.assertEqual(proven_margin_objects(page,tp),[])
                    self.assertEqual(len(exclude_margin_text(page,pl.pages[0]).chars),len(pl.pages[0].chars))
                    if mode=='body':self.assertTrue(needs_ocr(page)[0])

    def test_mixed_image_pages_keep_the_existing_ocr_route(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'mixed.pdf';c=canvas.Canvas(str(source),pagesize=(612,792))
            c.drawString(50,700,'Digital label')
            c.drawInlineImage(Image.new('RGB',(100,100),'gray'),50,100,width=500,height=500)
            c.setFillColorRGB(1,1,1);c.drawString(50,20,'Synthetic printer mark');c.save()
            with pdf.PdfDocument(source) as d,closing(d[0]) as page,closing(page.get_textpage()) as tp:
                self.assertEqual(proven_margin_objects(page,tp),[])
                self.assertTrue(needs_ocr(page)[0])
