import unittest
from copy import deepcopy
from ocr_table_overlap import suppress_table_text_duplicates


class TableOverlapTests(unittest.TestCase):
    def blocks(self):
        values=['Checklist heading','Set the switch to position 12.','Continue the inspection before restarting.']
        table=dict(kind='table',bbox=[40,40,540,340],rows=3,cols=1,
                   cells=[dict(row=i,col=0,rowspan=1,colspan=1,text=t) for i,t in enumerate(values)])
        children=[dict(kind='paragraph',bbox=[50,50+i*70,530,100+i*70],text=t)
                  for i,t in enumerate(values)]
        return [table,*children]

    def test_table_and_contained_text_are_not_exported_twice(self):
        blocks=self.blocks();original=deepcopy(blocks[0]['cells'])
        result=suppress_table_text_duplicates(blocks)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['cells'],original)
        self.assertEqual(result[0]['deduplicated_ocr_regions'],3)

    def test_changed_number_retains_evidence_and_requests_review(self):
        blocks=self.blocks();blocks[2]['text']=blocks[2]['text'].replace('12','13')
        result=suppress_table_text_duplicates(blocks)
        self.assertEqual(len(result),4)
        self.assertTrue(result[0]['ocr_overlap_review'])

    def test_same_phrase_elsewhere_and_small_matches_are_preserved(self):
        blocks=self.blocks();outside=deepcopy(blocks[1]);outside['bbox']=[50,400,530,450]
        result=suppress_table_text_duplicates([*blocks,outside])
        self.assertEqual(len(result),2);self.assertIs(result[-1],outside)
        table=deepcopy(blocks[0]);table['cells'].append(dict(text='Another long independent sentence '*20))
        self.assertEqual(len(suppress_table_text_duplicates([table,deepcopy(blocks[2])])),2)

    def test_conflicting_order_and_repeated_cell_labels_are_not_guessed(self):
        blocks=self.blocks();blocks[1]['text'],blocks[3]['text']=blocks[3]['text'],blocks[1]['text']
        self.assertEqual(len(suppress_table_text_duplicates(blocks)),4)
        blocks=self.blocks();blocks[0]['cells'].append(deepcopy(blocks[0]['cells'][1]))
        self.assertEqual(len(suppress_table_text_duplicates(blocks)),4)

    def test_only_quote_typography_is_normalized(self):
        blocks=self.blocks();blocks[0]['cells'][1]['text']='Check the operator’s display before restarting.'
        blocks[2]['text']="Check the operator's display before restarting."
        self.assertEqual(len(suppress_table_text_duplicates(blocks)),1)

    def test_word_boundary_disagreement_is_not_removed(self):
        blocks=self.blocks();blocks[0]['cells'][1]['text']='The item is nowhere near the switch.'
        blocks[2]['text']='The item is now here near the switch.'
        result=suppress_table_text_duplicates(blocks)
        self.assertEqual(len(result),4);self.assertTrue(result[0]['ocr_overlap_review'])

    def test_sign_changes_and_oversized_proofs_are_not_accepted(self):
        blocks=self.blocks();blocks[0]['cells'][1]['text']='-1234567890123';blocks[2]['text']='1234567890123'
        result=suppress_table_text_duplicates(blocks)
        self.assertEqual(len(result),4);self.assertTrue(result[0]['ocr_overlap_review'])
        blocks=self.blocks();blocks[0]['cells'][0]['text']='x'*200001
        self.assertIs(suppress_table_text_duplicates(blocks),blocks)

    def test_small_detector_padding_and_first_row_labels(self):
        blocks=self.blocks();blocks[0]['bbox']=[40,40,540,237]
        self.assertEqual(len(suppress_table_text_duplicates(blocks)),1)
        blocks=self.blocks();blocks[0]['cells'].append(dict(row=3,text='Independent body content '*100))
        blocks[1]['bbox']=[50,48,530,62]
        result=suppress_table_text_duplicates([blocks[0],blocks[1]])
        self.assertEqual(len(result),1)
        blocks=self.blocks();blocks[3]['bbox']=[50,345,530,400]
        result=suppress_table_text_duplicates(blocks)
        self.assertIn(blocks[3],result)
