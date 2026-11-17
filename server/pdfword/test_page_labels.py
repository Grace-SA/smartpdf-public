"""Numeric footer recovery preserves labels and rejects ambiguous source regions."""
import unittest
from types import SimpleNamespace
from lxml import etree as E
from native_page_labels import numeric_footer
from stirling_package import restore_numeric_footer, W, w, N, text


class PageLabelTests(unittest.TestCase):
    def word(self, value, top, bottom):
        return dict(text=value, x0=100, x1=120, top=top, bottom=bottom)

    def page(self, words):
        return SimpleNamespace(width=600, height=800, extract_words=lambda: words)

    def test_only_a_separated_bottom_label_is_evidence(self):
        body = self.word('Body', 60, 72)
        label = self.word('12', 770, 782)
        self.assertEqual(numeric_footer(self.page([body, label])), '12')
        for words in [[label], [body, self.word('12', 600, 612)],
                      [body, self.word('12 notes', 770, 782)],
                      [body, label, self.word('note', 770, 782)],
                      [self.word('nearby', 755, 768), label],
                      [body, self.word('12', 790, 805)]]:
            self.assertIsNone(numeric_footer(self.page(words)))

    def parts(self):
        body = E.fromstring(f'<w:body xmlns:w="{W}"><w:p><w:r><w:t>Body</w:t></w:r></w:p><w:tbl/><w:p><w:r><w:t>12</w:t></w:r></w:p><w:sectPr/></w:body>')
        types = E.fromstring('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        return body, {'[Content_Types].xml': types}

    def test_footer_is_preserved_with_valid_relationship_and_no_body_spill(self):
        body, parts = self.parts()
        before = text(body)
        restore_numeric_footer(parts, body, '12')
        self.assertEqual(before, text(body) + ' ' + text(parts['word/footer1.xml']))
        footer = parts['word/footer1.xml']
        self.assertEqual(footer[0][0].tag, w('pPr'))
        self.assertEqual(footer.find('.//w:spacing', N).get(w('before')), '0')
        self.assertIsNotNone(body.find('.//w:footerReference', N))
        self.assertEqual(len(parts['word/_rels/document.xml.rels']), 1)
        self.assertEqual(body[-2].find('.//w:spacing', N).get(w('line')), '20')

    def test_existing_footer_bookmark_or_wrong_label_is_untouched(self):
        for case in ['existing', 'bookmark', 'wrong', 'no_table']:
            body, parts = self.parts()
            if case == 'existing':
                parts['word/footer1.xml'] = E.Element(w('ftr'))
            elif case == 'bookmark':
                E.SubElement(body[-2], w('bookmarkStart'))
            elif case == 'no_table':
                body.remove(body.find(w('tbl')))
            before = E.tostring(body)
            restore_numeric_footer(parts, body, '99' if case == 'wrong' else '12')
            self.assertEqual(before, E.tostring(body))
