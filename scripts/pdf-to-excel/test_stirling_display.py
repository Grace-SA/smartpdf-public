"""Display subset tests, not assertions of original PDF semantic recovery."""

import datetime
import sys
import unittest
from decimal import Decimal, Inexact, Rounded, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server/pdf-to-excel"))
from stirling_display import DisplayError, display_text


class StirlingDisplayTests(unittest.TestCase):
    def test_actual_numeric_formats(self):
        for value, fmt, expected in [
            (1.2, "0.00", "1.20"),
            (0.125, "0.0%", "12.5%"),
            (1234.5, '"$"#,##0.00', "$1,234.50"),
            (-12.3, "0.00;(0.00)", "(12.30)"),
            (1363, "#,##0", "1,363"),
            (-82.1, "0.0;(0.0)", "(82.1)"),
        ]:
            self.assertEqual(display_text(value, fmt), expected)

    def test_strings_and_booleans_are_not_numeric(self):
        for text in ["001234", "123456789012345678", "01/02/2024", "=1+1"]:
            self.assertEqual(display_text(text), text)
        self.assertEqual(display_text(True), "TRUE")
        self.assertEqual(display_text(False), "FALSE")
        self.assertEqual(display_text(1), "1")
        with self.assertRaises(DisplayError):
            display_text(True, "0")

    def test_sections_zero_and_rounding(self):
        for value, expected in [(12.3, "12.30"), (-12.3, "(12.30)"), (0, "0.0")]:
            self.assertEqual(display_text(value, "0.00;(0.00);0.0"), expected)
        self.assertEqual(
            display_text(0, "0.0;(0.0)"), "0.0"
        )  # Source parentheses already lost.
        self.assertEqual(display_text(-12.3, "0.0;0.0"), "12.3")
        self.assertEqual(display_text(-12.3, "0.0;-0.0"), "-12.3")
        self.assertEqual(display_text(-12.3, "0.0"), "-12.3")
        self.assertEqual(display_text(2.675, "0.00"), "2.68")
        self.assertEqual(display_text(Decimal("1.005"), "0.00"), "1.01")
        self.assertEqual(display_text(-0.125, "0.0%;(0.0%)"), "(12.5%)")
        self.assertEqual(display_text(12.3, "\\€0.00"), "€12.30")

    def test_dates_explicit_no_hidden_time(self):
        value = datetime.datetime(2024, 1, 2)
        for fmt, expected in [
            ("mm\\/dd\\/yyyy", "01/02/2024"),
            ("dd/mm/yyyy", "02/01/2024"),
            ("yyyy-mm-dd", "2024-01-02"),
        ]:
            self.assertEqual(display_text(value, fmt), expected)
        for bad_value, fmt in [
            (value, "General"),
            (value, "m/d/yy"),
            (datetime.datetime(2024, 1, 2, 1), "mm/dd/yyyy"),
            (datetime.datetime(2024, 1, 2, tzinfo=datetime.UTC), "mm/dd/yyyy"),
            (45293, "mm/dd/yyyy"),
        ]:
            with self.assertRaises(DisplayError):
                display_text(bad_value, fmt)

    def test_nonzero_rounded_to_zero_rejected_without_sign_guess(self):
        for value in [-0.004, -0.0001, 0.004]:
            for fmt in ["0.00", "0.00;(0.00)", "0.00;(0.00);0.0", "0.00;-0.00;0.0"]:
                with (
                    self.subTest(value=value, fmt=fmt),
                    self.assertRaises(DisplayError),
                ):
                    display_text(value, fmt)
        with self.assertRaises(DisplayError):
            display_text(-0.000001, "0.0%")
        self.assertEqual(display_text(-0.006, "0.00"), "-0.01")
        self.assertEqual(display_text(0, "0.00;(0.00);0.0"), "0.0")

    def test_early_excel_dates_are_ambiguous(self):
        for date in [
            datetime.date(1899, 12, 31),
            datetime.date(1900, 1, 1),
            datetime.date(1900, 2, 28),
            datetime.datetime(1900, 2, 28),
        ]:
            with self.assertRaises(DisplayError):
                display_text(date, "mm/dd/yyyy")
        self.assertEqual(
            display_text(datetime.date(1900, 3, 1), "mm/dd/yyyy"), "03/01/1900"
        )

    def test_unknown_and_malformed_formats_reject(self):
        for fmt in [
            "",
            None,
            "0;",
            "0;0;0;@",
            "[Red]0",
            "[>1]0",
            "0E+00",
            "# ?/?",
            "0.##",
            "[$-409]0",
            '0"kg"',
            "(0)",
            "-0",
            "0;garbage",
            "0.0.0",
            '0%"$"',
            "0" * 129,
        ]:
            with self.subTest(fmt=fmt), self.assertRaises(DisplayError):
                display_text(12, fmt)

    def test_caller_decimal_context_does_not_round_input(self):
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(display_text(Decimal("1234.567"), "#,##0.00"), "1,234.57")
            with self.assertRaises(DisplayError):
                display_text(Decimal("1.234567890123456"), "0.00")

    def test_caller_decimal_limits_and_traps_do_not_change_results(self):
        # This library does not own the process-wide Decimal configuration.
        # Precision, exponent limits and traps must all remain caller-local.
        with localcontext() as context:
            context.prec = 2
            context.Emax = 2
            context.Emin = -2
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            self.assertEqual(display_text(Decimal("1234.567"), "#,##0.00"), "1,234.57")
            self.assertEqual(display_text(Decimal("0.000001"), "0.000000"), "0.000001")
            self.assertEqual(display_text(Decimal("0.125"), "0.0%"), "12.5%")
            with self.assertRaises(DisplayError):
                display_text(Decimal("1.234567890123456"), "0.00")
            self.assertEqual((context.prec, context.Emin, context.Emax), (2, -2, 2))
            self.assertTrue(context.traps[Inexact])
            self.assertTrue(context.traps[Rounded])

    def test_precision_and_nonfinite_refuse(self):
        for value in [
            123456789012345678,
            float("nan"),
            float("inf"),
            Decimal("NaN"),
            Decimal("1.234567890123456"),
            Decimal("1e-30"),
            Decimal("1e999999999"),
            None,
            object(),
        ]:
            with self.subTest(value=value), self.assertRaises(DisplayError):
                display_text(value, "0.00")
        for value in [1.2, 10000000000]:
            with self.assertRaises(DisplayError):
                display_text(value)
        self.assertEqual(display_text(999999999), "999999999")


if __name__ == "__main__":
    unittest.main()
