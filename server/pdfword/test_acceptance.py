"""Malformed metrics cannot certify general production readiness."""

import copy
import unittest

from acceptance import CATEGORIES, evaluate


def passing_report():
    # Synthetic gate exercise, not a source corpus or product quality score.
    row = dict(
        pages=5, categories=sorted(CATEGORIES), native=False,
        partition="held_out", frozen_before_development=True, status="accepted",
        independent_opc=True, visual_review=True, edit_reopen=True,
        ground_truth_verified=True,
        metrics=dict(reading_order=1.0, text_accuracy=1.0, cer=0.0,
                     cell_accuracy=1.0, teds=1.0, critical_errors=0),
    )
    return dict(
        documents=[dict(copy.deepcopy(row), family=f"synthetic-{i}") for i in range(120)],
        performance=dict(native_10page_warm_p95_seconds=5, ocr_10page_warm_p95_seconds=60),
        platform_checks=dict(microsoft_word=True, linux_gpu_isolation=True,
                             concurrent_load=True, cancellation_cleanup=True,
                             browser_regression=True),
    )


class AcceptanceTests(unittest.TestCase):
    def test_valid_synthetic_report_passes_gate_logic(self):
        self.assertTrue(evaluate(passing_report())["ready"])

    def test_out_of_range_ratios_do_not_inflate_acceptance(self):
        for metric, native in (("reading_order", False), ("text_accuracy", True),
                               ("cell_accuracy", False), ("teds", False), ("cer", False)):
            for value in (-0.1, 1.1, float("nan"), float("inf"), True, "1.0"):
                with self.subTest(metric=metric, value=value):
                    report = passing_report()
                    for row in report["documents"]:
                        row["native"] = native
                        row["metrics"][metric] = value
                    result = evaluate(report)
                    self.assertFalse(result["ready"])
                    self.assertEqual(result["accepted"], 0)

    def test_native_classification_must_be_explicit_boolean(self):
        for value in (None, "false", "true", 0, 1, [], {}):
            with self.subTest(value=value):
                report = passing_report()
                for row in report["documents"]:
                    row["native"] = value
                self.assertFalse(evaluate(report)["ready"])

    def test_critical_error_count_is_integer_not_false_or_float(self):
        for value in (False, 0.0, "0", None, -1, 1):
            with self.subTest(value=value):
                report = passing_report()
                for row in report["documents"]:
                    row["metrics"]["critical_errors"] = value
                self.assertFalse(evaluate(report)["ready"])

    def test_refusals_remain_in_the_denominator(self):
        report = passing_report()
        for row in report["documents"][:7]:
            row["status"] = "refused"
        self.assertFalse(evaluate(report)["ready"])


if __name__ == "__main__":
    unittest.main()
