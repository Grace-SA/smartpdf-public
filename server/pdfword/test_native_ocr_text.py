"""Native text may replace OCR prose only with independent region agreement."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import pdfplumber
import pypdfium2 as pdf
from native_ocr_text import reconcile
from test_worker import fixture


class NativeOcrTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.source=Path(self.tmp.name)/'source.pdf'
        fixture(self.source,content=b'BT /F1 12 Tf 48 700 Td (Verified text 123) Tj ET')
        self.doc=pdf.PdfDocument(self.source);self.native=pdfplumber.open(self.source)
    def tearDown(self):
        self.native.close();self.doc.close();self.tmp.cleanup()
    def block(self):return dict(kind='paragraph',text='Mistranscribed text 132',bbox=[40,70,200,110],source='ocr')
    def test_independent_region_preserves_exact_visible_text(self):
        block=self.block();self.assertEqual(reconcile(self.doc[0],self.native.pages[0],[block]),1)
        self.assertEqual(block['text'],'Verified text 123')
        self.assertEqual(''.join(r['text'] for r in block['runs']),block['text'])
    def test_overlapping_candidates_cannot_duplicate_native_text(self):
        blocks=[self.block(),self.block()]
        self.assertEqual(reconcile(self.doc[0],self.native.pages[0],blocks),0)
        self.assertTrue(all(b['source']=='ocr' for b in blocks))
    def test_sparse_native_label_cannot_replace_large_ocr_paragraph(self):
        block=self.block();block['text']='long scan paragraph '*100
        self.assertEqual(reconcile(self.doc[0],self.native.pages[0],[block]),0)
    def test_image_region_and_table_do_not_use_native_prose_replacement(self):
        p=self.native.pages[0]
        view=SimpleNamespace(dedupe_chars=p.dedupe_chars,images=[dict(x0=40,x1=200,top=70,bottom=110)])
        self.assertEqual(reconcile(self.doc[0],view,[self.block()]),0)
        block=self.block();block['kind']='table'
        self.assertEqual(reconcile(self.doc[0],p,[block]),0)
    def test_mismatched_independent_characters_keep_ocr(self):
        p=self.native.pages[0];chars=[dict(c) for c in p.chars];chars[0]['text']='X'
        view=SimpleNamespace(dedupe_chars=lambda **kw:SimpleNamespace(chars=chars),images=[])
        self.assertEqual(reconcile(self.doc[0],view,[self.block()]),0)

    def test_control_character_requires_blank_pixels_and_adjacent_background(self):
        for ink in (False, True):
            source=Path(self.tmp.name)/f'control-{ink}.pdf'
            content=b'BT /F1 12 Tf 48 700 Td (Verified text 123) Tj ET'
            if ink:content+=b' 0 g 180 700 4 12 re f'
            fixture(source,content=content)
            with pdf.PdfDocument(source) as doc,pdfplumber.open(source) as native:
                chars=list(native.pages[0].chars)
                chars.append(dict(chars[0],text='\x07',x0=180,x1=184,top=80,bottom=92))
                view=SimpleNamespace(dedupe_chars=lambda **kw:SimpleNamespace(chars=chars),images=[])
                self.assertEqual(reconcile(doc[0],view,[self.block()]),0 if ink else 1)

    def test_rtl_native_geometry_is_not_used_as_logical_reading_order(self):
        p=self.native.pages[0];chars=[dict(c) for c in p.chars]
        chars[0]['text']='א'
        view=SimpleNamespace(dedupe_chars=lambda **kw:SimpleNamespace(chars=chars),images=[])
        block=self.block()
        from unittest.mock import Mock
        page=Mock(wraps=self.doc[0])
        page.get_textpage.return_value=SimpleNamespace(get_text_bounded=lambda *args:''.join(c['text'] for c in chars),close=lambda:None)
        self.assertEqual(reconcile(page,view,[block]),0)
        self.assertEqual(block['source'],'ocr')
