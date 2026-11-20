import copy
import unittest
from types import SimpleNamespace
from lxml import etree as E
from native_table_titles import source_titles, restore_titles, tag, N

TITLE = 'Summary of current regional service outcomes'

def source(text=TITLE, left=0, right=300):
    table = SimpleNamespace(bbox=(0, 0, 300, 100), rows=[SimpleNamespace(cells=[(left, 0, right, 20), None, None]), object()], extract=lambda: [[text, None, None], ['a', 'b', 'c']])
    return SimpleNamespace(find_tables=lambda: [table])

def body():
    cells = ''.join('<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="1000"/><w:shd w:fill="FFCCCC"/><w:tcBorders><w:left w:val="nil"/><w:right w:val="nil"/></w:tcBorders></w:tcPr><w:p><w:r><w:t>'+value+'</w:t></w:r></w:p></w:tc>' for value in ['Summary of', 'current regional', 'service outcomes'])
    return E.fromstring(f'<w:tbl xmlns:w="{N["w"]}"><w:tblGrid><w:gridCol w:w="1000"/><w:gridCol w:w="1000"/><w:gridCol w:w="1000"/></w:tblGrid><w:tr>{cells}</w:tr><w:tr/></w:tbl>')

class TitleTests(unittest.TestCase):
    def test_source_requires_unique_spanning_non_numeric_title(self):
        self.assertEqual(len(source_titles(source())), 1)
        for page in [source(left=20), source(right=270), source(text=TITLE+' 123')]:
            self.assertFalse(source_titles(page))
        page = source(); table = page.find_tables()[0]; page.find_tables = lambda: [table, table]
        self.assertFalse(source_titles(page))
        other = source(text='A different structured table title here').find_tables()[0]
        page.find_tables = lambda: [table] + [other] * 127 + [table]
        self.assertFalse(source_titles(page))

    def test_repair_retains_text_and_grid(self):
        tree = body()
        self.assertEqual(restore_titles(tree, source_titles(source())), 1)
        cells = tree.findall('w:tr/w:tc', N)
        self.assertEqual(len(cells), 1)
        self.assertEqual(''.join(cells[0].xpath('.//w:t/text()', namespaces=N)), TITLE)
        self.assertEqual(cells[0].find('w:tcPr/w:gridSpan', N).get(tag('val')), '3')
        self.assertEqual(cells[0].find('w:tcPr/w:tcW', N).get(tag('w')), '3000')
        self.assertEqual(len(tree.findall('w:tblGrid/w:gridCol', N)), 3)
        self.assertEqual([E.QName(x).localname for x in cells[0].find(tag('tcPr'))][:2], ['tcW', 'gridSpan'])
        self.assertEqual(restore_titles(tree, source_titles(source())), 0)

    def test_ambiguous_rows_stay_unchanged(self):
        for kind in ['unverified', 'border', 'shade', 'merge', 'bookmark', 'duplicate']:
            tree = body()
            if kind == 'border': tree.find('w:tr/w:tc/w:tcPr/w:tcBorders/w:right', N).set(tag('val'), 'single')
            if kind == 'shade': tree.find('w:tr/w:tc/w:tcPr/w:shd', N).set(tag('fill'), 'FFFFFF')
            if kind == 'merge': E.SubElement(tree.find('w:tr/w:tc/w:tcPr', N), tag('vMerge'))
            if kind == 'bookmark': E.SubElement(tree.find('w:tr/w:tc/w:p', N), tag('bookmarkStart'))
            if kind == 'duplicate':
                wrapper = E.Element(tag('body')); wrapper.append(copy.deepcopy(tree)); wrapper.append(tree); tree = wrapper
            before = E.tostring(tree)
            self.assertEqual(restore_titles(tree, set() if kind == 'unverified' else source_titles(source())), 0, kind)
            self.assertEqual(E.tostring(tree), before)

    def test_split_word_is_not_repaired_by_inserting_a_space(self):
        tree = body()
        texts = tree.xpath('.//w:t', namespaces=N)
        texts[1].text = 'current regio'
        texts[2].text = 'nal service outcomes'
        before = E.tostring(tree)
        self.assertEqual(restore_titles(tree, source_titles(source())), 0)
        self.assertEqual(E.tostring(tree), before)
