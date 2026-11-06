import tempfile
import unittest
import zipfile
import io
from pathlib import Path
from layout import apply_no_wrap, nowrap_plan
from synthetic import nowrap_presentation, pack


class Shapes:
    def __init__(self, *items): self.items = items; self.Count = len(items)
    def getByIndex(self, index): return self.items[index]


class Shape:
    def __init__(self, name='Synthetic title', text='SYNTHETIC HEADING WITH WORDS', supported=True):
        self.Name = name; self.text = text; self.supported = supported; self.TextAutoGrowWidth = False
    def supportsService(self, name): return False
    def getPropertySetInfo(self): return self
    def hasPropertyByName(self, name): return self.supported and name == 'TextAutoGrowWidth'
    def getString(self): return self.text


class Document:
    def __init__(self, *pages): self.pages = Shapes(*pages)
    def getDrawPages(self): return self.pages


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'synthetic.pptx'; self.source.write_bytes(nowrap_presentation())

    def test_explicit_source_intent_and_manual_breaks(self):
        plan = nowrap_plan(self.source)
        self.assertTrue(plan[0]); self.assertFalse(plan[1]); self.assertTrue(plan[2])
        a, b, c = Shape(), Shape(), Shape(text='SYNTHETIC HEADING\nWITH WORDS')
        self.assertEqual(apply_no_wrap(Document(Shapes(a), Shapes(b), Shapes(c)), self.source), 2)
        self.assertTrue(a.TextAutoGrowWidth); self.assertFalse(b.TextAutoGrowWidth); self.assertTrue(c.TextAutoGrowWidth)
        self.assertEqual(c.text, 'SYNTHETIC HEADING\nWITH WORDS')
        self.assertEqual(apply_no_wrap(Document(Shapes(a), Shapes(b), Shapes(c)), self.source), 0)

    def test_changed_text_or_ambiguous_import_is_not_modified(self):
        for shapes in (Shapes(Shape(text='different synthetic text')), Shapes(Shape(), Shape()), Shapes(Shape(supported=False)), Shapes(Shape(name='renamed'))):
            self.assertEqual(apply_no_wrap(Document(shapes, Shapes(), Shapes()), self.source), 0)
            self.assertTrue(all(not s.TextAutoGrowWidth for s in shapes.items))

    def test_fixed_or_ambiguous_source_names_are_not_modified(self):
        with zipfile.ZipFile(io.BytesIO(nowrap_presentation())) as z:
            files = {n: z.read(n) for n in z.namelist()}
        files['ppt/slides/slide1.xml'] = files['ppt/slides/slide1.xml'].replace(b'<a:spAutoFit/>', b'<a:noAutofit/>')
        files['ppt/slides/slide3.xml'] = files['ppt/slides/slide3.xml'].replace(b'name=""', b'name="Synthetic title"')
        self.source.write_bytes(pack(files))
        self.assertEqual(nowrap_plan(self.source), [{}, {}, {}])

    def test_page_scope_must_match_before_any_change(self):
        shape = Shape()
        with self.assertRaisesRegex(RuntimeError, 'scope'):
            apply_no_wrap(Document(Shapes(shape)), self.source)
        self.assertFalse(shape.TextAutoGrowWidth)


if __name__ == '__main__': unittest.main()
