import importlib.util, unittest
from dark_contrast import prepare_dark_document

@unittest.skipUnless(importlib.util.find_spec('cv2'), 'Requires OCR preprocessing environment')
class Tests(unittest.TestCase):

    def setUp(self):
        global cv2, np
        import cv2, numpy as np

    def scan(self):
        im = np.full((600, 1000, 3), 17, dtype=np.uint8)
        for index, y in enumerate(range(55, 560, 80)):
            cv2.putText(im, 'Printed text 0123456789 and labels', (35 + index * 7, y), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)
        return im

    def test_dark_scan_and_quarter_turn_recover_contrast_without_moving_pixels(self):
        for im in [self.scan(), np.rot90(self.scan()).copy()]:
            out, meta = prepare_dark_document(im)
            self.assertTrue(meta['dark_contrast_stretched'])
            self.assertEqual(out.shape, im.shape)
            self.assertEqual(out.max(), 245)
            self.assertTrue(np.array_equal(np.all(im == 0, axis=2), np.all(out == 0, axis=2)))

    def test_monotonic_mapping_retains_thin_gray_edges(self):
        im = self.scan()
        im[im == 17] = 23
        im[100, 50:80] = np.arange(30)[:, None] % 24
        out, meta = prepare_dark_document(im)
        self.assertTrue(meta['dark_contrast_stretched'])
        for value in np.unique(im):
            self.assertEqual(len(np.unique(out[im == value])), 1)
        values = [int(out[im == value][0]) for value in np.unique(im)]
        self.assertEqual(values, sorted(set(values)))

    def test_clean_color_blank_and_grid_unchanged(self):
        dark = self.scan()
        colour = dark.copy()
        colour[:, :, 0] += 1
        grid = np.full_like(dark, 17)
        for y in range(20, 580, 40):
            cv2.line(grid, (20, y), (980, y), (0, 0, 0), 2)
        for x in range(20, 981, 80):
            cv2.line(grid, (x, 20), (x, 580), (0, 0, 0), 2)
        for im in [dark * 15, colour, np.zeros_like(dark), np.full_like(dark, 17), grid]:
            out, meta = prepare_dark_document(im)
            self.assertFalse(meta['dark_contrast_stretched'])
            self.assertTrue(np.array_equal(im, out))

    def test_dark_photograph_without_paper_peak_unchanged(self):
        rng = np.random.default_rng(12)
        gray = rng.integers(0, 24, (600, 1000), dtype=np.uint8)
        im = np.repeat(gray[:, :, None], 3, axis=2)
        out, meta = prepare_dark_document(im)
        self.assertFalse(meta['dark_contrast_stretched'])
        self.assertTrue(np.array_equal(im, out))

    def test_unknown_depth_unchanged(self):
        im = self.scan().astype(np.uint16)
        out, meta = prepare_dark_document(im)
        self.assertFalse(meta['dark_contrast_stretched'])
        self.assertTrue(np.array_equal(im, out))
if __name__ == '__main__':
    unittest.main()
