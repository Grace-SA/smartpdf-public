"""A figure crop retains small label descenders without absorbing prose."""
import tempfile
import unittest
from pathlib import Path
import pdfplumber
import pypdfium2 as pdf
from layout import include_figure_labels
from worker import checked_native_page, needs_ocr
from test_worker import fixture

class FigureLabelTests(unittest.TestCase):
    def word(self, box, text='9'):
        return dict(zip(['x0','top','x1','bottom'],box),text=text)
    def test_small_descender_expands_crop_to_full_label(self):
        self.assertEqual(include_figure_labels([[10,10,100,30]],[self.word([20,15,30,30.7])],200,200),[[10,10,100,30.7]])
    def test_large_extension_prose_and_page_edge_are_not_absorbed(self):
        for word in [self.word([20,15,30,34]),self.word([20,15,30,30.7],'long prose '*20),self.word([20,-1,30,15])]:
            self.assertEqual(include_figure_labels([[10,10,100,30]],[word],200,200),[[10,10,100,30]])
    def test_neighbouring_word_prevents_expansion(self):
        words=[self.word([20,15,30,30.7]),self.word([60,30.5,80,40],'body')]
        self.assertEqual(include_figure_labels([[10,10,100,30]],words,200,200),[[10,10,100,30]])
    def test_native_numeric_coverage_passes_only_with_complete_figure_crop(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'synthetic.pdf'
            fixture(source,content=b'.8 g 50 699 80 15 re f 0 g BT /F1 18 Tf 70 700 Td (9) Tj ET BT /F1 12 Tf 48 600 Td (Editable body remains) Tj ET')
            with pdf.PdfDocument(source) as doc,pdfplumber.open(source) as native:
                blocks=checked_native_page(doc[0],native.pages[0],needs_ocr(doc[0])[1])
                image=next(b for b in blocks if b['kind']=='image')
                glyph=next(c for c in native.pages[0].chars if c['text']=='9')
                self.assertGreaterEqual(image['bbox'][3],glyph['bottom'])
                self.assertIn('Editable body remains',' '.join(b.get('text','') for b in blocks))
