"""Run in the provisioned Paddle environment, which supplies OpenCV and NumPy."""

import importlib.util
import unittest

from scan_quality import enhance


@unittest.skipUnless(
    importlib.util.find_spec("cv2"), "Requires the OCR preprocessing environment"
)
class ScanTests(unittest.TestCase):
    def test_black_borders_and_halftone_figures_are_not_illumination(self):
        import cv2
        import numpy as np

        image = np.full((600, 400, 3), 255, dtype=np.uint8)
        image[500:] = 0
        image[220:480, 20:150] = 0
        for y in range(30, 480, 30):
            cv2.putText(
                image,
                "123.45 AB",
                (170, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                1,
            )
        for source in (image, cv2.GaussianBlur(image, (3, 3), 0.5)):
            result, report = enhance(source)
            self.assertFalse(report["enhanced"])
            self.assertTrue(np.array_equal(source, result))

    def test_clean_and_colour_pages_are_unchanged(self):
        import numpy as np

        for colour in ((245, 245, 245), (50, 180, 250)):
            image = np.full((300, 200, 3), colour, dtype=np.uint8)
            result, report = enhance(image)
            self.assertFalse(report["enhanced"])
            self.assertTrue(np.array_equal(image, result))

    def test_shadow_reduced_without_erasing_thin_strokes(self):
        import cv2
        import numpy as np

        image = np.repeat(
            np.tile(np.linspace(130, 245, 400), (600, 1)).astype(np.uint8)[:, :, None],
            3,
            axis=2,
        )
        for y in range(40, 580, 30):
            cv2.putText(
                image,
                "123.45 AB",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (60, 60, 60),
                1,
            )
        result, report = enhance(image)
        self.assertTrue(report["enhanced"])
        self.assertLess(np.std(result[590, :, 0]), np.std(image[590, :, 0]) / 3)
        strokes = image[:, :, 0] == 60
        self.assertTrue(np.all(result[:, :, 0][strokes] < 150))
        self.assertEqual(result.shape, image.shape)
