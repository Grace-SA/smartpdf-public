"""Original synthetic regression tests for the independent quality gate."""

from __future__ import annotations
import copy
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from openpyxl import Workbook
from corpus import cases, generate
from evaluate import run, FROZEN_CASE_IDS
from validate import QualityError, verify_result, SS, REL


BASE = {
    "pages": 1,
    "page_expectations": [{"page": 1, "status": "converted"}],
    "tables": [
        {
            "page": 1,
            "sheet": "Table_1",
            "rows": [
                ["Name", "Value", "Note"],
                ["00001", "=1+1", ""],
                ["测试", "1.234,56", "A\nB"],
            ],
            "merges": [],
        }
    ],
}
REPORT = {
    "pages": [{"page": 1, "status": "converted"}],
    "tables": [{"sheet": "Table_1", "page": 1}],
}


def golden(expected=BASE):
    book = Workbook()
    book.remove(book.active)
    for table in expected["tables"]:
        sheet = book.create_sheet(table["sheet"])
        for r, row in enumerate(table["rows"], 1):
            for c, value in enumerate(row, 1):
                cell = sheet.cell(r, c, value)
                cell.data_type = "s"
        for merge in table.get("merges", []):
            sheet.merge_cells(merge)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def rewrite(data, part, function):
    stream = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for entry in source.infolist():
            content = source.read(entry)
            if entry.filename == part:
                content = function(content)
            target.writestr(entry.filename, content)
    return stream.getvalue()


def edit_sheet(data, edit):
    def modify(content):
        root = ET.fromstring(content)
        edit(root)
        return ET.tostring(root, encoding="utf-8")

    return rewrite(data, "xl/worksheets/sheet1.xml", modify)


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.data = golden()

    def reject(self, code, data=None, report=None, expected=None):
        with self.assertRaisesRegex(QualityError, "^" + code + "$"):
            verify_result(
                expected or BASE,
                report or REPORT,
                data if data is not None else self.data,
            )

    def test_exact_literals_unicode_multiline_and_empty(self):
        self.assertEqual(
            verify_result(BASE, REPORT, self.data),
            {"pages": 1, "tables": 1, "cells": 9},
        )

    def test_missing_page_report(self):
        self.reject("page_coverage", report={"pages": [], "tables": REPORT["tables"]})

    def test_duplicate_pages(self):
        expected = {**BASE, "pages": 2}
        self.reject(
            "page_order",
            expected=expected,
            report={**REPORT, "pages": [REPORT["pages"][0]] * 2},
        )

    def test_failed_page_is_not_success(self):
        self.reject(
            "page_not_converted",
            report={**REPORT, "pages": [{"page": 1, "status": "needs_ocr"}]},
        )

    def test_wrong_source_page(self):
        self.reject(
            "table_provenance",
            report={**REPORT, "tables": [{"sheet": "Table_1", "page": 2}]},
        )

    def test_missing_table(self):
        self.reject("table_coverage", report={**REPORT, "tables": []})

    def test_cell_loss(self):
        data = edit_sheet(
            self.data, lambda root: root.find(f"{{{SS}}}sheetData/{{{SS}}}row").clear()
        )
        self.reject("cell_mismatch", data=data)

    def test_empty_cell_shift(self):
        expected = copy.deepcopy(BASE)
        expected["tables"][0]["rows"][1] = ["00001", "", "=1+1"]
        self.reject("cell_mismatch", expected=expected)

    def test_formula_injection(self):
        def inject(root):
            cell = root.find(f"{{{SS}}}sheetData/{{{SS}}}row/{{{SS}}}c")
            ET.SubElement(cell, f"{{{SS}}}f").text = "1+1"

        self.reject("formula_or_link", data=edit_sheet(self.data, inject))

    def test_numeric_coercion(self):
        def coerce(root):
            cell = root.find(f"{{{SS}}}sheetData/{{{SS}}}row/{{{SS}}}c")
            cell.clear()
            cell.set("r", "A1")
            ET.SubElement(cell, f"{{{SS}}}v").text = "1"

        self.reject("coerced_value", data=edit_sheet(self.data, coerce))

    def test_unexpected_extra_value(self):
        def add(root):
            row = root.find(f"{{{SS}}}sheetData/{{{SS}}}row")
            cell = ET.SubElement(row, f"{{{SS}}}c", {"r": "D1", "t": "inlineStr"})
            value = ET.SubElement(cell, f"{{{SS}}}is")
            ET.SubElement(value, f"{{{SS}}}t").text = "extra"

        self.reject("extra_content", data=edit_sheet(self.data, add))

    def test_duplicate_cell(self):
        def duplicate(root):
            row = root.find(f"{{{SS}}}sheetData/{{{SS}}}row")
            row.append(copy.deepcopy(row[0]))

        self.reject("duplicate_cell", data=edit_sheet(self.data, duplicate))

    def test_hidden_row(self):
        self.reject(
            "hidden_row",
            data=edit_sheet(
                self.data,
                lambda root: root.find(f"{{{SS}}}sheetData/{{{SS}}}row").set(
                    "hidden", "1"
                ),
            ),
        )

    def test_hidden_sheet(self):
        self.reject(
            "hidden_sheet",
            data=rewrite(
                self.data,
                "xl/workbook.xml",
                lambda data: data.replace(b'state="visible"', b'state="hidden"'),
            ),
        )

    def test_external_relationship(self):
        def inject(data):
            root = ET.fromstring(data)
            ET.SubElement(
                root,
                f"{{{REL}}}Relationship",
                {
                    "Id": "rUnsafe",
                    "Target": "https://example.invalid",
                    "TargetMode": "External",
                    "Type": "externalLink",
                },
            )
            return ET.tostring(root)

        self.reject(
            "external_relationship",
            data=rewrite(self.data, "xl/_rels/workbook.xml.rels", inject),
        )

    def test_dtd_entities(self):
        self.reject(
            "xml_entities",
            data=rewrite(
                self.data,
                "xl/workbook.xml",
                lambda data: b'<!DOCTYPE x [<!ENTITY x "test">]>' + data,
            ),
        )

    def test_utf16_entities_rejected(self):
        self.reject(
            "xml_encoding",
            data=rewrite(
                self.data,
                "xl/workbook.xml",
                lambda data: data.decode().encode("utf-16"),
            ),
        )

    def test_invalid_zip(self):
        self.reject("invalid_zip", data=b"not xlsx")

    def test_absent_output(self):
        with self.assertRaisesRegex(QualityError, "zip_size"):
            verify_result(BASE, REPORT, None)

    def test_zip_limits(self):
        with patch("validate.MAX_ZIP_BYTES", 1):
            self.reject("zip_size")
        with patch("validate.MAX_EXPANDED_BYTES", 1):
            self.reject("zip_expansion")
        with patch("validate.MAX_PART_BYTES", 1):
            self.reject("part_size")
        with patch("validate.MAX_PARTS", 1):
            self.reject("zip_parts")
        with patch("validate.MAX_CELLS", 1):
            self.reject("cell_budget")

    def test_zip_traversal(self):
        stream = io.BytesIO(self.data)
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr("../escape.xml", "<x/>")
        self.reject("part_path", data=stream.getvalue())

    def test_embedded_binary(self):
        stream = io.BytesIO(self.data)
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr("xl/vbaProject.bin", b"synthetic")
        self.reject("active_or_embedded_part", data=stream.getvalue())

    def test_merge_geometry(self):
        expected = copy.deepcopy(BASE)
        expected["tables"][0]["rows"][0] = ["Header", "", ""]
        expected["tables"][0]["merges"] = ["A1:C1"]
        self.assertEqual(verify_result(expected, REPORT, golden(expected))["cells"], 9)
        wrong = copy.deepcopy(expected)
        wrong["tables"][0]["merges"] = []
        self.reject("merge_mismatch", data=golden(expected), expected=wrong)

    def test_shared_strings(self):
        # Independent handcrafted shared-string encoding of the first cell.
        data = edit_sheet(self.data, lambda root: None)

        def shared(root):
            cell = root.find(f"{{{SS}}}sheetData/{{{SS}}}row/{{{SS}}}c")
            cell.clear()
            cell.attrib.update({"r": "A1", "t": "s"})
            ET.SubElement(cell, f"{{{SS}}}v").text = "0"

        data = edit_sheet(data, shared)

        def add_type(data):
            root = ET.fromstring(data)
            ET.SubElement(
                root,
                "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
                {
                    "PartName": "/xl/sharedStrings.xml",
                    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml",
                },
            )
            return ET.tostring(root)

        data = rewrite(data, "[Content_Types].xml", add_type)

        def add_relation(data):
            root = ET.fromstring(data)
            ET.SubElement(
                root,
                f"{{{REL}}}Relationship",
                {
                    "Id": "rShared",
                    "Target": "sharedStrings.xml",
                    "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings",
                },
            )
            return ET.tostring(root)

        data = rewrite(data, "xl/_rels/workbook.xml.rels", add_relation)
        stream = io.BytesIO(data)
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr(
                "xl/sharedStrings.xml", f'<sst xmlns="{SS}"><si><t>Name</t></si></sst>'
            )
        self.assertEqual(verify_result(BASE, REPORT, stream.getvalue())["cells"], 9)

    def test_real_baseline_frozen_denominator(self):
        result = run()
        self.assertEqual(result["conversion_total"], 16)
        self.assertEqual(result["refusal_total"], 3)
        self.assertEqual(result["refusal_passed"], 3)
        self.assertEqual(result["synthetic_corpus_gate"], "fail")
        failed = {r["id"] for r in result["results"] if not r["passed"]}
        self.assertEqual(
            failed,
            {
                "borderless",
                "scanned-table",
                "mixed-native-scan",
                "rotated-page",
                "narrative-page",
            },
        )

    def test_empty_or_duplicate_corpus_is_never_success(self):
        for inventory in ([], [cases()[0]] * len(FROZEN_CASE_IDS)):
            with patch("evaluate.cases", return_value=inventory):
                with self.assertRaisesRegex(QualityError, "corpus_inventory"):
                    run()

    def test_manifest_cannot_be_empty(self):
        self.reject(
            "missing_content_type",
            data=rewrite(
                self.data,
                "[Content_Types].xml",
                lambda data: b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
            ),
        )

    def test_wrong_workbook_content_type(self):
        self.reject(
            "workbook_content_type",
            data=rewrite(
                self.data,
                "[Content_Types].xml",
                lambda data: data.replace(
                    b"spreadsheetml.sheet.main+xml", b"spreadsheetml.invalid.main+xml"
                ),
            ),
        )

    def test_broken_package_workbook_relationship(self):
        self.reject(
            "package_workbook_target",
            data=rewrite(
                self.data,
                "_rels/.rels",
                lambda data: data.replace(b"xl/workbook.xml", b"xl/absent.xml"),
            ),
        )

    def test_bad_style_index(self):
        self.reject(
            "cell_style_reference",
            data=edit_sheet(
                self.data,
                lambda root: root.find(f"{{{SS}}}sheetData/{{{SS}}}row/{{{SS}}}c").set(
                    "s", "9999"
                ),
            ),
        )

    def test_zero_height(self):
        self.reject(
            "invisible_dimension",
            data=edit_sheet(
                self.data,
                lambda root: root.find(f"{{{SS}}}sheetData/{{{SS}}}row").set("ht", "0"),
            ),
        )

    def test_zero_width(self):
        def invisible(root):
            cols = ET.SubElement(root, f"{{{SS}}}cols")
            ET.SubElement(cols, f"{{{SS}}}col", {"min": "1", "max": "3", "width": "0"})

        self.reject("invisible_dimension", data=edit_sheet(self.data, invisible))

    def test_default_hidden_rows(self):
        self.reject(
            "hidden_default_rows",
            data=edit_sheet(
                self.data,
                lambda root: root.find(f"{{{SS}}}sheetFormatPr").set("zeroHeight", "1"),
            ),
        )

    def test_duplicate_table_source_fails(self):
        case = next(c for c in cases() if c["id"] == "multipage")
        wrong = copy.deepcopy(case)
        wrong["tables"][1]["rows"] = wrong["tables"][0]["rows"]
        report = {
            "pages": case["page_expectations"],
            "tables": [
                {"sheet": t["sheet"], "page": t["page"]} for t in case["tables"]
            ],
        }
        self.reject("cell_mismatch", expected=case, report=report, data=golden(wrong))

    def test_non_tabular_page_is_not_inferred_blank(self):
        expected = copy.deepcopy(BASE)
        expected.pop("page_expectations")
        self.reject("oracle_page_disposition", expected=expected)

    def test_generator_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            for case in cases():
                if case.get("refusal") == "encrypted":
                    continue  # Encryption salts deliberately need not be fixed.
                a, b = Path(directory) / "a.pdf", Path(directory) / "b.pdf"
                generate(case, a)
                generate(case, b)
                self.assertEqual(a.read_bytes(), b.read_bytes(), case["id"])


if __name__ == "__main__":
    unittest.main()
