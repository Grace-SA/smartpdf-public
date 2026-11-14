"""Synthetic nested-grid label-order proof and conservative exclusions."""
import copy
import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server/pdf-to-excel'))
from layout_nested_guard import verify_nested_labels
from layout_tables import LayoutError


def fixture(lines=('Under', 'surveillance')):
    chars = []
    bounds = []
    for row, word in enumerate(lines):
        top = 15 + row * 18
        for col, ch in enumerate(word):
            chars.append(dict(text=ch, x0=10 + col*6, x1=15 + col*6,
                              top=top, bottom=top+10, doctop=top, size=10,
                              fontname='Synthetic', upright=True,
                              matrix=(1, 0, 0, 1, 10+col*6, 200-top)))
        bounds.append((9, top-1, 10+len(word)*6, top+11))
    parent = dict(closedGrid=True, bbox=(0, 0, 200, 200), widths=[100, 100], heights=[100, 100],
                  cells=[dict(r=r, c=c, rs=1, cs=1, text='\n'.join(lines) if (r,c)==(0,0) else '')
                         for r in range(2) for c in range(2)])
    child = dict(closedGrid=True, bbox=(120, 20, 180, 80), widths=[30, 30], heights=[30, 30],
                 cells=[dict(r=r, c=c, rs=1, cs=1, text='') for r in range(2) for c in range(2)])
    pieces = [dict(r=len(lines)-1-i, c=0, rs=1, cs=1, text=word, sourceTextCandidate=bounds[i])
              for i, word in enumerate(lines)]
    model = dict(cells=pieces)
    page = SimpleNamespace(chars=chars, images=[], annots=[], rotation=0,
                           bbox=(0, 0, 200, 200), cropbox=None, width=200, height=200)
    return model, [parent, child], page


class NestedGuardTests(unittest.TestCase):
    def test_reverse_order_refuses_without_changing_any_value(self):
        model, native, page = fixture()
        before = copy.deepcopy((model, native, page.chars))
        with self.assertRaisesRegex(LayoutError, 'reversed a source label'):
            verify_nested_labels(model, native, page)
        self.assertEqual((model, native, page.chars), before)

    def test_correct_multiline_and_repeated_words_are_not_rejected(self):
        for lines in [('Under', 'surveillance'), ('North', 'Region'), ('Under', 'Under')]:
            model, native, page = fixture(lines)
            for i, c in enumerate(model['cells']):
                c['r'] = i
            verify_nested_labels(model, native, page)
        model, native, page = fixture(('Under', 'Under'))
        verify_nested_labels(model, native, page)

    def test_repeated_word_counts_do_not_mask_actual_reordering(self):
        model, native, page = fixture(('Under', 'surveillance', 'Under'))
        for c, row in zip(model['cells'], [1, 2, 0]):
            c['r'] = row
        with self.assertRaises(LayoutError):
            verify_nested_labels(model, native, page)
        model['cells'][1]['text'] = 'surveillance surveillance'
        verify_nested_labels(model, native, page)  # Changed multiset is not this proof.

    def test_no_guess_when_words_or_numeric_values_differ(self):
        for lines in [('12', '34'), ('Under', 'Überwachung')]:
            verify_nested_labels(*fixture(lines))
        model, native, page = fixture(); model['cells'][0]['text'] = 'Unknown'
        verify_nested_labels(model, native, page)

    def test_real_pdf_grid_and_final_adapter_refuse_injected_reversal(self):
        import pdfplumber
        from reportlab.pdfgen import canvas
        from convert import ruled_tables
        from layout_tables import extract_layout_tables
        from docling.datamodel.base_models import ConversionStatus
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'nested.pdf'
            drawing = canvas.Canvas(str(source), pagesize=(200, 200))
            for x in (20, 100, 180): drawing.line(x, 20, x, 180)
            for y in (20, 100, 180): drawing.line(20, y, 180, y)
            drawing.setFont('Helvetica', 10)
            drawing.drawString(30, 165, 'Under'); drawing.drawString(30, 147, 'surveillance')
            for x in (115, 140, 165): drawing.line(x, 115, x, 165)
            for y in (115, 140, 165): drawing.line(115, y, 165, y)
            for x, y, text in ((120,150,'A'), (145,150,'B'), (120,125,'1'), (145,125,'2')):
                drawing.drawString(x, y, text)
            drawing.drawString(30, 65, 'Value 12'); drawing.drawString(110, 65, 'Record')
            drawing.save(); original = source.read_bytes()
            with pdfplumber.open(source) as doc:
                page = doc.pages[0]; native = ruled_tables(page)
                self.assertEqual(len(native), 2)
                pieces = []
                for row, word, low, high in ((1,'Under',20,40),(0,'surveillance',40,60)):
                    chars = [g for g in page.chars if g['x0'] < 100 and low < g['top'] < high]
                    box = (min(g['x0'] for g in chars), min(g['top'] for g in chars),
                           max(g['x1'] for g in chars), max(g['bottom'] for g in chars))
                    pieces.append(dict(r=row,c=0,rs=1,cs=1,text=word,sourceTextCandidate=box))
                model = dict(bbox=native[0]['bbox'], widths=[80,80], heights=[80,80], cells=pieces)
                # Inject a bad neural reconstruction, but keep real PDF reading,
                # native closed grids, glyph geometry and final adapter guard.
                predicted = SimpleNamespace(data=SimpleNamespace(num_rows=2,num_cols=2),
                                            prov=[SimpleNamespace(page_no=1)], model_dump=lambda: {})
                result = SimpleNamespace(status=ConversionStatus.SUCCESS,
                                         document=SimpleNamespace(tables=[predicted]))
                converter = SimpleNamespace(convert=lambda *args, **kwargs: result)
                with patch('layout_dense.dense_grid', return_value=None), patch(
                    'layout_tables.converter_for', return_value=converter
                ), patch('layout_tables.refine_predictions', return_value=[{}]), patch(
                    'layout_grid.has_vertical_headers', return_value=False
                ), patch('layout_open.recover_open_grid', return_value=None), patch(
                    'layout_tables.adapt_table', return_value=model
                ):
                    with self.assertRaisesRegex(LayoutError, 'reversed a source label'):
                        extract_layout_tables(source, [0], 'unused', doc.pages, ruled_tables)
            self.assertEqual(source.read_bytes(), original)

    def test_geometry_and_closed_grid_counterexamples(self):
        mutations = [
            lambda m,n,p: n[0].update(closedGrid=False),
            lambda m,n,p: n[1].update(closedGrid=False),
            lambda m,n,p: n[1].update(bbox=(100,20,160,80)),
            lambda m,n,p: n[1].update(bbox=(10,10,90,90), widths=[40,40], heights=[40,40]),
            lambda m,n,p: n[0]['cells'].pop(),
            lambda m,n,p: n.append(copy.deepcopy(n[1])),
            lambda m,n,p: m['cells'][0].update(sourceTextCandidate=(0,0,110,100)),
            lambda m,n,p: m['cells'][0].update(sourceTextCandidate=m['cells'][1]['sourceTextCandidate']),
            lambda m,n,p: m['cells'][0].update(c=1),
            lambda m,n,p: p.images.append(dict(x0=0,top=0,x1=100,bottom=100)),
            lambda m,n,p: p.annots.append(dict(x0=0,top=0,x1=100,bottom=100)),
            lambda m,n,p: p.chars[0].update(size=14),
            lambda m,n,p: p.chars[0].update(upright=False),
            lambda m,n,p: p.chars[0].update(matrix=(1,0.1,0,1,10,185)),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                model, native, page = fixture(); mutate(model,native,page)
                verify_nested_labels(model,native,page)


if __name__ == '__main__':
    unittest.main()
