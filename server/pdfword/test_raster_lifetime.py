from pathlib import Path
import tempfile, unittest, json, zipfile
from unittest.mock import patch
from reportlab.pdfgen import canvas
from PIL import Image
from docx import Document
import worker
from exporter import export_word

class Tests(unittest.TestCase):

    def test_page_rasters_released_while_retained_crops_remain_editable_export_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / 'input.pdf'
            work = root / 'work'
            work.mkdir()
            count = 20
            c = canvas.Canvas(str(pdf), pagesize=(300, 400))
            for page in range(count):
                c.setFillColorRGB(0, 0, 1)
                c.rect(50, 300, 50, 50, fill=1, stroke=0)
                c.drawString(40, 250, f'Page {page + 1}')
                c.showPage()
            c.save()
            owner = self

            class FakeOCR:
                calls = 0

                def recognize(self, image, width, height, complex_layout=False):
                    owner.assertEqual(len(list(work.glob('page-*.png'))), 1)
                    owner.assertEqual(len(list(work.glob('p*-b1.png'))), self.calls)
                    self.calls += 1
                    return [dict(kind='paragraph', text=f'Editable page {self.calls}', bbox=[40, 140, 200, 155], source='oxr'), dict(kind='image', bbox=[50, 50, 100, 100], source='oxr')]
            with patch.object(worker, 'needs_ocr', return_value=(True, True, True)):
                model = worker.parse_pdf(pdf, work, ocr=FakeOCR())
            self.assertFalse(list(work.glob('page-*.png')))
            self.assertEqual(len(list(work.glob('p*-b1.png'))), count)
            for path in work.glob('p*-b1.png'):
                with Image.open(path) as image:
                    self.assertEqual(image.getpixel((image.width // 2, image.height // 2)), (0, 0, 255))
            out = root / 'result.docx'
            report = export_word(model, out, work)
            self.assertEqual(report['pages'], count)
            self.assertEqual(report['images'], count)
            text = '\n'.join((p.text for p in Document(out).paragraphs))
            for page in range(count):
                self.assertIn(f'Editable page {page + 1}', text)

    def test_cancelled_parse_keeps_no_next_page_raster(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / 'input.pdf'
            c = canvas.Canvas(str(pdf), pagesize=(300, 400))
            c.drawString(40, 200, 'First')
            c.showPage()
            c.drawString(40, 200, 'Second')
            c.save()
            cancel = root / 'cancel'

            class FakeOCR:

                def recognize(self, *args, **kwargs):
                    cancel.touch()
                    return [dict(kind='paragraph', text='first', bbox=[40, 190, 100, 210], source='oxr')]
            with patch.object(worker, 'needs_ocr', return_value=(True, True, True)), self.assertRaisesRegex(worker.Rejected, 'cancelled'):
                worker.parse_pdf(pdf, root, ocr=FakeOCR(), cancel=cancel)
            self.assertFalse(list(root.glob('page-*.png')))
if __name__ == '__main__':
    unittest.main()
