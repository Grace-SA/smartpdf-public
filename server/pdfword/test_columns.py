import tempfile
import unittest
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from columns import column_flow
from exporter import export_word


class ColumnTests(unittest.TestCase):
    def blocks(self):
        blocks = [
            dict(id="title", kind="heading", bbox=[40, 30, 550, 60], text="Title")
        ]
        for col, x in enumerate([40, 330]):
            for row in range(3):
                blocks.append(
                    dict(
                        id=f"c{col}-{row}",
                        kind="paragraph",
                        bbox=[x, 90 + row * 30, x + 200, 110 + row * 30],
                        text=f"Column {col} paragraph {row}",
                    )
                )
        return blocks

    def test_heading_and_columns_preserve_order_and_editability(self):
        blocks = self.blocks()
        planned = column_flow(blocks, 612)
        self.assertEqual(
            [b["id"] for b in planned if "id" in b], [b["id"] for b in blocks]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "columns.docx"
            export_word(
                dict(
                    schema=2,
                    pages=[dict(index=0, width=612, height=792, blocks=blocks)],
                ),
                path,
                tmp,
            )
            doc = Document(path)
            self.assertEqual(
                [c.get(qn("w:num")) for c in doc.element.iter(qn("w:cols"))],
                ["1", "2", "1"],
            )
            self.assertEqual(
                len(
                    [
                        b
                        for b in doc.element.iter(qn("w:br"))
                        if b.get(qn("w:type")) == "column"
                    ]
                ),
                1,
            )
            self.assertIn(
                "Column 1 paragraph 2", " ".join(p.text for p in doc.paragraphs)
            )

    def test_overlapping_full_width_figure_does_not_force_columns(self):
        blocks = self.blocks() + [
            dict(id="overlap", kind="image", bbox=[100, 100, 500, 180])
        ]
        self.assertFalse(
            any(b["kind"] == "columns_start" for b in column_flow(blocks, 612))
        )
