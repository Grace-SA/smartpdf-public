"""Lossless run compaction must not cross formatting or semantic boundaries."""
import tempfile
import unittest
from pathlib import Path
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from exporter import compact_text_runs


class RunCompactionTests(unittest.TestCase):
    def test_long_uniform_text_stays_identical_after_save_and_reopen(self):
        doc = Document()
        p = doc.add_paragraph()
        for i in range(3000):
            run = p.add_run(f' word{i}')
            run.font.name = 'Arial'
            run.font.size = Pt(10)
        expected = p.text
        before = len(doc.element.xml)
        compact_text_runs(doc)
        self.assertEqual(p.text, expected)
        self.assertEqual(len(p.runs), 1)
        self.assertLess(len(doc.element.xml), before / 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.docx'
            doc.save(path)
            self.assertEqual(Document(path).paragraphs[0].text, expected)

    def test_breaks_tabs_and_significant_spaces_survive(self):
        doc = Document()
        p = doc.add_paragraph()
        for value in [' a ', '\tb\n', ' c ', '\n\td']:
            p.add_run(value)
        expected = p.text
        compact_text_runs(doc)
        self.assertEqual(p.text, expected)
        self.assertEqual(len(p.runs), 1)
        self.assertEqual(len(p._p.findall('.//' + qn('w:br'))), 2)
        self.assertEqual(len(p._p.findall('.//' + qn('w:tab'))), 2)

    def test_formatting_bookmarks_fields_and_math_are_merge_barriers(self):
        doc = Document()
        p = doc.add_paragraph()
        p.add_run('plain')
        p.add_run('bold').bold = True
        p.add_run('plain')
        start = OxmlElement('w:bookmarkStart')
        start.set(qn('w:id'), '1')
        start.set(qn('w:name'), 'smartpdf_page_1')
        p._p.append(start)
        p.add_run('marked')
        field = p.add_run()
        field._r.append(OxmlElement('w:fldChar'))
        p.add_run('after field')
        p._p.append(OxmlElement('m:oMath'))
        p.add_run('after math')
        before = p._p.xml
        compact_text_runs(doc)
        self.assertEqual(p._p.xml, before)
