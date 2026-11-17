"""Synthetic independent-grid agreement and fail-closed fallback boundaries."""
import copy
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from stream_tables import StreamTables, qualified_tables, header_spans


def proposal():
    grid = [["Region", "First", "Second"]] + [["Area", str(10+i), str(20+i)] for i in range(4)]
    grid.append(["Footnote outside the data", "", ""])
    cols = [[20, 120], [120, 220], [220, 320]]
    rows = [[180-i*20, 160-i*20] for i in range(6)]
    words = [dict(text=text, x0=cols[c][0]+5, x1=cols[c][0]+5+len(text)*3,
                  top=200-rows[r][0]+5, bottom=200-rows[r][0]+13, chars=[])
             for r, row in enumerate(grid) for c, text in enumerate(row) if text]
    return dict(rotation="", pdf_size=[400, 200], grid=grid, cols=cols, rows=rows), words


class StreamTableTests(unittest.TestCase):
    def setUp(self):
        self.page = SimpleNamespace(width=400, height=200)
        self.proposal, self.words = proposal()

    def test_agreed_cells_keep_widths_and_leave_footnotes_outside(self):
        tables = qualified_tables(self.page, self.words, [self.proposal])
        self.assertEqual(len(tables), 1)
        self.assertEqual((tables[0]['rows'], tables[0]['cols']), (5, 3))
        self.assertEqual(tables[0]['widths'], [100]*3)
        self.assertNotIn('Footnote', ''.join(c['text'] for c in tables[0]['cells']))
        self.assertEqual([c['text'] for c in tables[0]['cells'][-3:]], ['Area', '13', '23'])

    def test_swapped_numbers_fail_even_with_same_whole_table_text(self):
        self.proposal['grid'][1][1:3] = ['20', '10']
        self.assertEqual(qualified_tables(self.page, self.words, [self.proposal]), [])

    def test_reordered_digits_inside_one_cell_are_not_equivalent(self):
        self.proposal['grid'][3][1] = '21'  # Native cell is 12: same characters, wrong value.
        self.assertEqual(qualified_tables(self.page, self.words, [self.proposal]), [])

    def test_missing_native_word_fails(self):
        self.assertEqual(qualified_tables(self.page, self.words[:-2], [self.proposal]), [])

    def test_parallel_prose_is_not_numeric_table(self):
        for row in self.proposal['grid']:
            row[:] = ['Parallel', 'Prose', 'Columns']
        self.assertEqual(qualified_tables(self.page, self.words, [self.proposal]), [])

    def test_geometry_rotation_nonfinite_and_overlapping_rows_fail(self):
        for key, value in [('rotation', 'clockwise'), ('pdf_size', [200, 400]),
                           ('cols', [[20, float('nan')], [120, 220], [220, 320]]),
                           ('rows', [[180, 160]]*6)]:
            candidate = copy.deepcopy(self.proposal)
            candidate[key] = value
            with self.subTest(key=key):
                self.assertEqual(qualified_tables(self.page, self.words, [candidate]), [])

    def test_duplicate_proposal_does_not_duplicate_table(self):
        self.assertEqual(len(qualified_tables(self.page, self.words, [self.proposal]*2)), 1)

    def test_spanning_header_needs_one_matching_phrase_and_owner(self):
        words = [dict(text='Group', x0=100, x1=120, top=20, bottom=28, chars=[]),
                 dict(text='heading', x0=128, x1=149, top=20, bottom=28, chars=[])]
        cells = header_spans(words, ['Group heading', '', ''], self.proposal['cols'], 0, self.page)
        self.assertEqual((cells[0]['col'], cells[0]['colspan'], cells[0]['text']), (0, 2, 'Group heading'))
        self.assertIsNone(header_spans(words, ['', '', 'Group heading'], self.proposal['cols'], 0, self.page))

    def test_numeric_header_disagreement_is_not_fixed_by_merging(self):
        words = [dict(text='2025', x0=110, x1=130, top=20, bottom=28, chars=[])]
        self.assertIsNone(header_spans(words, ['2025', '', ''], self.proposal['cols'], 0, self.page))

    def test_outer_table_rules_keep_unconnected_glyphs_and_connected_plots(self):
        from layout import reconstructed_rules
        def line(x0, top, x1, bottom):
            return dict(x0=x0, top=top, x1=x1, bottom=bottom)
        perimeter = [line(18, 18, 322, 18), line(18, 18, 18, 140),
                     line(322, 18, 322, 140), line(18, 140, 322, 140)]
        glyph = line(80, 125, 81, 135)
        page = SimpleNamespace(lines=perimeter+[glyph], rects=[])
        tables = [dict(bbox=[20, 20, 320, 120])]
        self.assertEqual(reconstructed_rules(page, tables), {id(x) for x in perimeter})
        page.lines.append(line(18, 130, 200, 130))
        self.assertEqual(reconstructed_rules(page, tables), set())

    def test_no_helper_is_an_empty_optional_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch('stream_tables.subprocess.run') as run:
            cache = StreamTables('input.pdf')
            self.assertEqual(cache.proposals(0), [])
            self.assertEqual(cache.proposals(1), [])
            run.assert_not_called()

    def test_failed_helper_is_not_retried_for_each_page(self):
        with patch.dict(os.environ, PDFWORD_TABLE_PYTHON='python'), patch(
                'stream_tables.subprocess.run', side_effect=subprocess.TimeoutExpired('python', 30)) as run:
            cache = StreamTables('input.pdf')
            for index in range(200):
                self.assertEqual(cache.proposals(index), [])
            self.assertEqual(run.call_count, 1)
