import tempfile
import unittest
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from math_export import equation, segments, unsupported, UnsupportedMath
from exporter import export_word


class InlineMathTests(unittest.TestCase):
    def test_editable_fraction_root_and_script_structure(self):
        value = equation(r"\frac{QK^{T}}{\sqrt{d_{k}}}+x_i^2")
        self.assertEqual(len(list(value.iter(qn("m:f")))), 1)
        self.assertEqual(len(list(value.iter(qn("m:rad")))), 1)
        self.assertEqual(len(list(value.iter(qn("m:sSubSup")))), 1)
        denominator = value.find(".//" + qn("m:den"))
        self.assertEqual("".join(denominator.itertext()), "dk")
        self.assertFalse(unsupported(r"Use $d_{k}$ and $\frac{1}{\sqrt{d_{k}}}$ here."))
        self.assertFalse(unsupported(r"Footnote $^{4}$"))
        self.assertIn(
            "expected value", "".join(equation(r"\text{expected value}").itertext())
        )

    def test_unknown_math_and_currency_are_not_silently_rewritten(self):
        value = r"Before $\unknown{x}$ after"
        self.assertEqual("".join(t for t, _, _ in segments(value)), value)
        self.assertTrue(unsupported(value))
        currency = list(segments("Costs $5 and $10."))
        self.assertEqual("".join(t for t, _, _ in currency), "Costs $5 and $10.")
        self.assertTrue(all(formula is None and not failed for _, formula, failed in currency))
        for value in (r"\frac{x}", r"x^{2", r"x_1_2", "{ " * 40 + "x" + "}" * 40):
            with self.assertRaises(UnsupportedMath):
                equation(value)

    def test_math_survives_document_save_and_reopen(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "math.docx"
            model = dict(
                schema=2,
                pages=[
                    dict(
                        index=0,
                        width=612,
                        height=792,
                        blocks=[
                            dict(
                                id="math",
                                kind="paragraph",
                                bbox=[40, 40, 550, 100],
                                text=r"Value $x_i^2+\frac{1}{\sqrt{d_k}}$ remains editable.",
                            )
                        ],
                    )
                ],
            )
            export_word(model, output, temp)
            doc = Document(output)
            self.assertEqual(len(list(doc.element.iter(qn("m:oMath")))), 1)
            self.assertEqual(doc.paragraphs[0].text, "Value  remains editable.")
            doc.paragraphs[0].add_run(" Edit retained.")
            doc.save(output)
            self.assertEqual(len(list(Document(output).element.iter(qn("m:oMath")))), 1)
