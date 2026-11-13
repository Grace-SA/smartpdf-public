"""Synthetic, original fixtures only. No public or private document assets."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np
from grid_probe import infer

class GridProbeTests(unittest.TestCase):
    def run_grid(self, image):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'input.png';cv2.imwrite(str(p),image)
            tsv=root/'ocr.tsv';tsv.write_text('level\ttext\n')
            with patch('grid_probe.subprocess.run',return_value=SimpleNamespace(stdout='synthetic')):
                return infer(p,tsv,root)

    def grid(self):
        a=np.full((400,400),255,np.uint8)
        for i in [40,160,280]:
            cv2.line(a,(40,i),(280,i),0,2)
            cv2.line(a,(i,40),(i,280),0,2)
        return a

    def test_original_full_grid(self):
        r=self.run_grid(self.grid());self.assertEqual(r['status'],'grid')
        self.assertEqual(len(r['cell_crop_cells']),2)

    def test_no_grid(self):
        self.assertEqual(self.run_grid(np.full((400,400),255,np.uint8))['status'],'no_rectangular_grid')

    def test_merged_cell_not_fabricated(self):
        a=self.grid();a[43:157,158:163]=255
        self.assertNotEqual(self.run_grid(a)['status'],'grid')

    def test_small_gap_rejected_after_review(self):
        # Regression: old 95% completeness accepted a broken separator.
        a=self.grid();a[43:49,158:163]=255
        r=self.run_grid(a)
        self.assertNotEqual(r['status'],'grid')

    def test_cell_budget(self):
        with patch('grid_probe.lines',return_value=list(range(0,300,10))):
            self.assertEqual(self.run_grid(self.grid())['status'],'cell_budget_exceeded')

    def test_oversized(self):
        self.assertEqual(self.run_grid(np.zeros((4001,4000),np.uint8))['status'],'invalid_or_oversized_image')

if __name__=='__main__':unittest.main()
