"""Already recognized OCR margins must support, not hide, repeated margins."""
import unittest
from layout import repeated_margins


class MixedMarginTests(unittest.TestCase):
    def pages(self):
        return [dict(index=i, width=600, height=800, blocks=[
            dict(kind='paragraph', bbox=[40,100,500,200], text='Body'),
            dict(kind='footer' if i<3 else 'paragraph', bbox=[40,760,60,775], text=str(i+1))
        ]) for i in range(6)]

    def test_existing_ocr_footers_support_native_page_labels(self):
        pages = self.pages()
        before = [[b['text'] for b in p['blocks']] for p in pages]
        repeated_margins(pages)
        self.assertTrue(all(p['blocks'][-1]['kind']=='footer' for p in pages))
        self.assertEqual(before, [[b['text'] for b in p['blocks']] for p in pages])

    def test_wrong_edge_and_unrelated_footer_text_do_not_supply_evidence(self):
        for wrong_edge in (False, True):
            pages = self.pages()
            for page in pages[:3]:
                if wrong_edge:
                    page['blocks'][-1]['kind'] = 'header'
                else:
                    page['blocks'][-1]['text'] = 'Different footer'
            repeated_margins(pages)
            self.assertTrue(all(p['blocks'][-1]['kind']=='paragraph' for p in pages[3:]))

    def test_digit_only_original_is_not_reclassified(self):
        pages = self.pages()
        for page in pages:
            page['blocks'] = [page['blocks'][-1]]
            page['blocks'][0]['kind'] = 'paragraph'
        repeated_margins(pages)
        self.assertTrue(all(p['blocks'][0]['kind']=='paragraph' for p in pages))
