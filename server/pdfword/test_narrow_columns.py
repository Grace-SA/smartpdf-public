"""Synthetic regressions for narrow, persistent prose-column gutters."""
import unittest
from collections import Counter
from columns import column_flow
from layout import words_to_blocks


def word(text, x, top, width=38, size=12):
    return dict(text=text, x0=x, x1=x+width, top=top, bottom=top+size,
                chars=[dict(size=size, fontname='Helvetica')])


def prose():
    return [word(f'{side}{row}{col}text', x+col*46, 70+row*18 + (6 if side == 'R' and row % 2 else 0))
            for side, x in [('L', 78), ('R', 308)]
            for row in range(8) for col in range(5)]


class NarrowColumnTests(unittest.TestCase):
    def test_narrow_gutter_keeps_column_text_separate_and_ordered(self):
        words = prose()
        blocks = words_to_blocks(words, 612, 792)
        self.assertFalse(any('L0' in b['text'] and 'R0' in b['text'] for b in blocks))
        text = ' '.join(b['text'] for b in blocks)
        self.assertLess(text.index('L74text'), text.index('R00text'))
        self.assertEqual(Counter(text.split()), Counter(w['text'] for w in words))
        for b in blocks:
            self.assertEqual(b['text'], ''.join(r['text'] for r in b['runs']))

    def test_narrow_prose_columns_export_as_two_columns(self):
        blocks = [dict(kind='paragraph', text='Substantial prose sentence ' * 3,
                       bbox=[left, 70+row*40+(6 if left>300 else 0), right, 90+row*40])
                  for left,right in [(56, 303), (306, 555)] for row in range(4)]
        flow = column_flow(blocks, 612)
        self.assertEqual([b['count'] for b in flow if b['kind']=='columns_start'], [2])
        self.assertEqual(sum(b['kind']=='column_break' for b in flow), 1)

    def test_long_paired_description_rows_are_not_split_as_prose(self):
        words = [word(f'{side}{row}description', x+col*64, 50+row*18, width=60)
                 for side,x in [('Description',50),('Definition',308)]
                 for row in range(6) for col in range(4)]
        blocks = words_to_blocks(words,612,792)
        joined = ' '.join(b['text'] for b in blocks)
        self.assertLess(joined.index('Definition0'),joined.index('Description1'))

    def test_short_grid_does_not_get_narrow_prose_exemption(self):
        blocks = [dict(kind='paragraph', text='Code', bbox=[left,70+row*40,right,90+row*40])
                  for left,right in [(56,303),(306,555)] for row in range(4)]
        self.assertEqual(column_flow(blocks,612), blocks)

    def test_full_width_text_disables_global_gutter_split(self):
        words = prose() + [word('spanning',290,40,width=60)]
        blocks = words_to_blocks(words,612,792)
        # Do not move a full-width heading behind either column.
        self.assertEqual(blocks[0]['text'],'spanning')
        self.assertEqual(Counter(' '.join(b['text'] for b in blocks).split()),
                         Counter(w['text'] for w in words))

    def test_bullet_stays_with_text_despite_other_column_baseline(self):
        words=prose()
        words.extend([word('•',90,230,width=5),word('Bullet',108,231,width=35),
                      word('content',148,231,width=40),word('Right',308,228,width=35)])
        blocks=words_to_blocks(words,612,792)
        bullets=[b for b in blocks if b['kind']=='list']
        self.assertEqual(len(bullets),1)
        self.assertEqual(bullets[0]['text'],'• Bullet content')


if __name__ == '__main__':
    unittest.main()
