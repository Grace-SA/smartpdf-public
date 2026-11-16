import importlib.util
import unittest

from scan_orientation import guarded_angle, line_axis, rotate_quarter


class DecisionTests(unittest.TestCase):
    def test_uncertain_rotation_cannot_overrule_clear_horizontal_lines(self):
        evidence = dict(horizontal_ratio=3)
        for proposed in (90, 270):
            self.assertEqual(guarded_angle(proposed, .77, evidence), (0, True))

    def test_axis_cannot_infer_upside_down_or_overrule_strong_prediction(self):
        evidence = dict(horizontal_ratio=3)
        self.assertEqual(guarded_angle(180, .7, evidence), (180, False))
        self.assertEqual(guarded_angle(90, .99, evidence), (90, False))
        self.assertEqual(guarded_angle(270, .7, None), (270, False))
        self.assertEqual(guarded_angle(90, .7, dict(horizontal_ratio=.3)), (90, False))

    def test_very_weak_quarter_turn_requires_consistent_horizontal_evidence(self):
        for angle in (90, 270):
            self.assertEqual(guarded_angle(angle, .49, dict(horizontal_ratio=1.5)), (0, True))
            self.assertEqual(guarded_angle(angle, .5, dict(horizontal_ratio=1.5)), (angle, False))
            self.assertEqual(guarded_angle(angle, .49, dict(horizontal_ratio=1.49)), (angle, False))
            self.assertEqual(guarded_angle(angle, .49, None), (angle, False))
        self.assertEqual(guarded_angle(180, .49, dict(horizontal_ratio=3)), (180, False))

    def test_invalid_model_result_is_rejected(self):
        for angle, confidence in [(45, .8), (90, float("nan")), (0, 1.1)]:
            with self.assertRaises(ValueError):
                guarded_angle(angle, confidence, None)


@unittest.skipUnless(importlib.util.find_spec("cv2"), "Requires OCR preprocessing environment")
class GeometryTests(unittest.TestCase):
    def text_image(self):
        import cv2
        import numpy as np

        image = np.full((600, 1000, 3), 255, dtype=np.uint8)
        for index, y in enumerate(range(55, 560, 80)):
            cv2.putText(image, "Printed text 0123456789 and labels", (35 + index * 7, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)
        return image

    def test_measured_text_axis_protects_upright_but_allows_sideways(self):
        source = self.text_image()
        upright = line_axis(source)
        self.assertIsNotNone(upright)
        self.assertEqual(guarded_angle(270, .77, upright), (0, True))
        sideways = line_axis(rotate_quarter(source, 90))
        self.assertIsNotNone(sideways)
        self.assertLess(sideways["horizontal_ratio"], 1)
        self.assertEqual(guarded_angle(270, .77, sideways), (270, False))

    def test_rotation_is_exact_and_invertible_at_all_right_angles(self):
        import numpy as np

        source = np.arange(7 * 11 * 3, dtype=np.uint8).reshape(7, 11, 3)
        for angle in (0, 90, 180, 270):
            rotated = rotate_quarter(source, angle)
            self.assertEqual(sorted(rotated.ravel()), sorted(source.ravel()))
            self.assertTrue(np.array_equal(rotate_quarter(rotated, (360-angle) % 360), source))

    def test_blank_colour_and_table_rules_are_not_text_line_evidence(self):
        import cv2
        import numpy as np

        blank = np.full((600, 1000, 3), 255, dtype=np.uint8)
        coloured = blank.copy(); coloured[:] = (30, 150, 220)
        grid = blank.copy()
        for y in range(20, 580, 40):
            cv2.line(grid, (20, y), (980, y), (0, 0, 0), 2)
        for x in range(20, 981, 80):
            cv2.line(grid, (x, 20), (x, 580), (0, 0, 0), 2)
        for source in (blank, coloured, grid):
            self.assertIsNone(line_axis(source))

    def test_preparation_guard_runs_before_optional_unwarp_without_second_rotation(self):
        import cv2
        import json
        import numpy as np
        import os
        import sys
        import tempfile
        import types
        from pathlib import Path
        from unittest.mock import Mock, patch
        import prepare_image

        source = self.text_image()
        orientation = Mock()
        orientation.predict.return_value = iter([dict(label_names=["270"], scores=[.77])])
        unwarp = Mock()

        def predict(image):
            self.assertTrue(np.array_equal(image, source))
            return iter([dict(output_img=image)])

        unwarp.predict.side_effect = predict
        module = types.ModuleType("paddleocr")
        module.DocImgOrientationClassification = Mock(return_value=orientation)
        module.DocPreprocessor = Mock(return_value=unwarp)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, paddleocr=module), \
                patch.dict(os.environ, PDFWORD_PADDLE_UNWARP="1"), \
                patch.object(prepare_image, "_pipeline", None), \
                patch.object(prepare_image, "_orientation", None):
            image, output = Path(tmp) / "image.png", Path(tmp) / "output.json"
            cv2.imwrite(str(image), source)
            prepare_image.main(dict(images=[str(image)], output=str(output), model_root=tmp))
            report = json.loads(Path(str(output) + ".quality.json").read_text())
            self.assertEqual(report["orientation_applied"], 0)
            self.assertTrue(report["orientation_rejected"])
            self.assertTrue(np.array_equal(cv2.imread(str(image)), source))
            self.assertFalse(module.DocPreprocessor.call_args.kwargs["use_doc_orientation_classify"])


if __name__ == "__main__":
    unittest.main()
