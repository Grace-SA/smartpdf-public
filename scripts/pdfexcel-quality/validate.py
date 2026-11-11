"""Independent, bounded OOXML and page-coverage gate for PDF-to-Excel candidates.

No converter dependency is used here. Expected values come from synthetic fixture
construction, never from the candidate parser. This is an evaluation tool, not a
sandbox for untrusted uploads.
"""

from __future__ import annotations

import io
import math
import posixpath
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
DOCREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_PART_BYTES = 8 * 1024 * 1024
MAX_PARTS = 256
MAX_CELLS = 100_000
CELL = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})\Z")


class QualityError(ValueError):
    """Stable, content-free diagnostic; do not include source text or filenames."""


def require(condition, code):
    if not condition:
        raise QualityError(code)


def xml(data):
    # Reject entity/DTD declarations before parsing. UTF-16/32 XML is not part
    # of this evaluation contract and must not bypass the declaration check.
    require(b"\x00" not in data, "xml_encoding")
    require(not re.search(rb"<!\s*(?:DOCTYPE|ENTITY)", data, re.I), "xml_entities")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise QualityError("invalid_xml") from exc


def positive_dimension(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise QualityError("invalid_dimension")
    require(math.isfinite(number) and number > 0, "invisible_dimension")


def coordinate(reference):
    match = CELL.fullmatch(reference or "")
    require(match is not None, "cell_reference")
    column = 0
    for letter in match[1]:
        column = column * 26 + ord(letter) - 64
    row = int(match[2])
    require(column <= 16384 and row <= 1048576, "cell_reference")
    return row, column


def cell_text(element):
    require(element.find(f"{{{SS}}}f") is None, "formula_present")
    kind = element.get("t", "n")
    if kind == "inlineStr":
        value = element.find(f"{{{SS}}}is")
        if value is None:
            return ""  # Empty inline-string cells are a legal blank encoding.
        # Phonetic annotations are not displayed cell content.
        return "".join(
            child.text or ""
            if child.tag == f"{{{SS}}}t"
            else "".join(t.text or "" for t in child.findall(f"{{{SS}}}t"))
            if child.tag == f"{{{SS}}}r"
            else ""
            for child in value
        )
    value = element.find(f"{{{SS}}}v")
    if value is None or value.text is None:
        require(kind in ("n", "s", "str"), "cell_type")
        return ""
    # A candidate must preserve literals, not guess dates/numeric identifiers.
    require(kind in ("s", "str"), "coerced_value")
    return value.text


@dataclass(frozen=True)
class Sheet:
    cells: dict
    merges: frozenset


def read_workbook(data):
    require(isinstance(data, bytes) and 0 < len(data) <= MAX_ZIP_BYTES, "zip_size")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise QualityError("invalid_zip") from exc
    with archive:
        parts = archive.infolist()
        require(0 < len(parts) <= MAX_PARTS, "zip_parts")
        names = [part.filename for part in parts]
        require(len(names) == len(set(names)), "duplicate_part")
        require(
            sum(part.file_size for part in parts) <= MAX_EXPANDED_BYTES, "zip_expansion"
        )
        roots = {}
        for part in parts:
            name = part.filename
            require(
                not (
                    name.startswith("/")
                    or "\\" in name
                    or any(bit in ("", ".", "..") for bit in name.split("/"))
                ),
                "part_path",
            )
            require(
                not part.flag_bits & 1 and part.file_size <= MAX_PART_BYTES, "part_size"
            )
            require(name.endswith((".xml", ".rels")), "active_or_embedded_part")
            try:
                # Read at most the budget even if metadata is malformed.
                with archive.open(part) as handle:
                    content = handle.read(MAX_PART_BYTES + 1)
                require(len(content) <= MAX_PART_BYTES, "part_size")
                roots[name] = xml(content)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                raise QualityError("invalid_zip") from exc
        require(
            "[Content_Types].xml" in roots and "xl/workbook.xml" in roots,
            "missing_workbook",
        )
        manifest = roots["[Content_Types].xml"]
        require(manifest.tag == f"{{{CT}}}Types", "content_types_root")
        types = {}
        defaults = {}
        for item in manifest:
            if item.tag == f"{{{CT}}}Override":
                name = item.get("PartName", "")
                require(
                    name.startswith("/")
                    and name[1:] in roots
                    and name[1:] not in types,
                    "content_type_part",
                )
                types[name[1:]] = item.get("ContentType")
            elif item.tag == f"{{{CT}}}Default":
                extension = item.get("Extension")
                require(extension and extension not in defaults, "content_type_default")
                defaults[extension] = item.get("ContentType")
            else:
                raise QualityError("content_type_element")
        for name in roots:
            if name != "[Content_Types].xml":
                require(
                    types.get(name, defaults.get(name.rsplit(".", 1)[-1])),
                    "missing_content_type",
                )
        require(
            types.get("xl/workbook.xml")
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
            "workbook_content_type",
        )
        package = roots.get("_rels/.rels")
        require(
            package is not None and package.tag == f"{{{REL}}}Relationships",
            "package_relationships",
        )
        office = [
            item for item in package if item.get("Type") == f"{DOCREL}/officeDocument"
        ]
        require(
            len(office) == 1
            and office[0].get("Target", "").lstrip("/") == "xl/workbook.xml",
            "package_workbook_target",
        )
        require(roots["xl/workbook.xml"].tag == f"{{{SS}}}workbook", "workbook_root")
        require(
            roots["xl/workbook.xml"].find(f"{{{SS}}}definedNames") is None
            or not len(roots["xl/workbook.xml"].find(f"{{{SS}}}definedNames")),
            "defined_names",
        )
        styles = roots.get("xl/styles.xml")
        require(
            styles is not None and styles.tag == f"{{{SS}}}styleSheet", "missing_styles"
        )
        xfs = styles.find(f"{{{SS}}}cellXfs")
        require(xfs is not None and len(xfs), "cell_styles")
        for xf in xfs:
            for attribute, collection in (
                ("fontId", "fonts"),
                ("fillId", "fills"),
                ("borderId", "borders"),
                ("xfId", "cellStyleXfs"),
            ):
                index = xf.get(attribute, "0")
                group = styles.find(f"{{{SS}}}{collection}")
                require(
                    index.isascii()
                    and index.isdigit()
                    and len(index) < 10
                    and group is not None
                    and int(index) < len(group),
                    "style_reference",
                )
            require(xf.get("numFmtId", "0") in ("0", "49"), "unsupported_number_format")
        for root in roots.values():
            for item in root.iter():
                require(
                    item.tag not in (f"{{{SS}}}f", f"{{{SS}}}externalReference"),
                    "formula_or_link",
                )
                content_type = item.get("ContentType", "").lower()
                require(
                    not any(
                        word in content_type
                        for word in (
                            "macroenabled",
                            "vba",
                            "oleobject",
                            "activex",
                            "externallink",
                        )
                    ),
                    "active_content_type",
                )
                if item.tag == f"{{{REL}}}Relationship":
                    require(
                        item.get("TargetMode", "Internal") == "Internal",
                        "external_relationship",
                    )
                    require(
                        not any(
                            word in item.get("Type", "").lower()
                            for word in (
                                "externallink",
                                "hyperlink",
                                "oleobject",
                                "vba",
                                "activex",
                            )
                        ),
                        "active_relationship",
                    )
        relationships = roots.get("xl/_rels/workbook.xml.rels")
        require(
            relationships is not None
            and relationships.tag == f"{{{REL}}}Relationships",
            "missing_relationships",
        )
        targets = {}
        for rel in relationships:
            rid = rel.get("Id")
            require(rid and rid not in targets, "duplicate_relationship")
            target = rel.get("Target", "")
            require(
                target
                and "\\" not in target
                and "#" not in target
                and "?" not in target,
                "relationship_target",
            )
            resolved = posixpath.normpath(
                target.lstrip("/") if target.startswith("/") else "xl/" + target
            )
            require(
                not resolved.startswith("../") and resolved in roots,
                "relationship_target",
            )
            targets[rid] = (resolved, rel.get("Type"))
        shared = []
        if "xl/sharedStrings.xml" in roots:
            require(
                types.get("xl/sharedStrings.xml")
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml",
                "shared_strings_content_type",
            )
            require(
                any(
                    path == "xl/sharedStrings.xml" and kind == f"{DOCREL}/sharedStrings"
                    for path, kind in targets.values()
                ),
                "shared_strings_relationship",
            )
            require(
                roots["xl/sharedStrings.xml"].tag == f"{{{SS}}}sst",
                "shared_strings_root",
            )
            for item in roots["xl/sharedStrings.xml"]:
                # Reuse the exact string rules without treating phonetics as data.
                wrapper = ET.Element(f"{{{SS}}}c", {"t": "inlineStr"})
                value = ET.SubElement(wrapper, f"{{{SS}}}is")
                value.extend(list(item))
                shared.append(cell_text(wrapper))
        sheets = {}
        used_targets = set()
        sheet_list = roots["xl/workbook.xml"].find(f"{{{SS}}}sheets")
        require(sheet_list is not None and len(sheet_list), "missing_sheets")
        total_cells = 0
        for item in sheet_list:
            name = item.get("name")
            require(
                name and name.casefold() not in {n.casefold() for n in sheets},
                "duplicate_sheet",
            )
            require(item.get("state", "visible") == "visible", "hidden_sheet")
            target, kind = targets.get(item.get(f"{{{DOCREL}}}id"), (None, None))
            require(
                kind == f"{DOCREL}/worksheet" and target not in used_targets,
                "worksheet_target",
            )
            used_targets.add(target)
            require(
                types.get(target)
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
                "worksheet_content_type",
            )
            root = roots[target]
            require(root.tag == f"{{{SS}}}worksheet", "worksheet_root")
            formatting = root.find(f"{{{SS}}}sheetFormatPr")
            if formatting is not None:
                require(
                    formatting.get("zeroHeight", "0") not in ("1", "true"),
                    "hidden_default_rows",
                )
                if "defaultRowHeight" in formatting.attrib:
                    positive_dimension(formatting.get("defaultRowHeight"))
            cells = {}
            for row in root.findall(f"{{{SS}}}sheetData/{{{SS}}}row"):
                require(row.get("hidden", "0") not in ("1", "true"), "hidden_row")
                if "ht" in row.attrib:
                    positive_dimension(row.get("ht"))
                for element in row:
                    require(element.tag == f"{{{SS}}}c", "unexpected_cell")
                    style = element.get("s", "0")
                    require(
                        style.isascii()
                        and style.isdigit()
                        and len(style) < 10
                        and int(style) < len(xfs),
                        "cell_style_reference",
                    )
                    ref = element.get("r")
                    position = coordinate(ref)
                    require(position not in cells, "duplicate_cell")
                    value = cell_text(element)
                    if element.get("t") == "s" and value:
                        require(
                            value.isascii() and value.isdigit() and len(value) < 10,
                            "shared_string_index",
                        )
                        index = int(value)
                        require(index < len(shared), "shared_string_index")
                        value = shared[index]
                    cells[position] = value
                    total_cells += 1
                    require(total_cells <= MAX_CELLS, "cell_budget")
            for column in root.findall(f"{{{SS}}}cols/{{{SS}}}col"):
                require(column.get("hidden", "0") not in ("1", "true"), "hidden_column")
                if "width" in column.attrib:
                    positive_dimension(column.get("width"))
            merges = set()
            for merge in root.findall(f"{{{SS}}}mergeCells/{{{SS}}}mergeCell"):
                ref = merge.get("ref", "")
                require(ref.count(":") == 1, "merge_reference")
                start, end = (coordinate(point) for point in ref.split(":"))
                require(start[0] <= end[0] and start[1] <= end[1], "merge_reference")
                require(ref not in merges, "duplicate_merge")
                merges.add(ref)
            sheets[name] = Sheet(cells, frozenset(merges))
        return sheets


def verify_result(expected, report, workbook):
    """Validate a complete conversion against a frozen, synthetic oracle."""
    require(isinstance(report, dict), "report_schema")
    pages = report.get("pages")
    require(
        isinstance(pages, list) and len(pages) == expected["pages"], "page_coverage"
    )
    require(all(isinstance(page, dict) for page in pages), "page_schema")
    require(
        [page.get("page") for page in pages] == list(range(1, expected["pages"] + 1)),
        "page_order",
    )
    tables = report.get("tables")
    require(isinstance(tables, list), "table_schema")
    expected_tables = expected["tables"]
    require(len(tables) == len(expected_tables), "table_coverage")
    expected_pages = expected.get("page_expectations")
    require(
        isinstance(expected_pages, list) and len(expected_pages) == expected["pages"],
        "oracle_page_disposition",
    )
    for page, expected_page in zip(pages, expected_pages):
        require(
            all(page.get(key) == value for key, value in expected_page.items()),
            "page_not_converted",
        )
    require(all(isinstance(table, dict) for table in tables), "table_schema")
    expected_sources = [(t["sheet"], t["page"]) for t in expected_tables]
    require(
        [(t.get("sheet"), t.get("page")) for t in tables] == expected_sources,
        "table_provenance",
    )
    sheets = read_workbook(workbook)
    require(set(sheets) == {t["sheet"] for t in expected_tables}, "sheet_coverage")
    for table in expected_tables:
        actual = sheets[table["sheet"]]
        rows = table["rows"]
        require(rows and all(len(row) == len(rows[0]) for row in rows), "oracle_shape")
        expected_cells = {
            (r, c): value
            for r, row in enumerate(rows, 1)
            for c, value in enumerate(row, 1)
        }
        require(
            all(
                actual.cells.get(key, "") == value
                for key, value in expected_cells.items()
            ),
            "cell_mismatch",
        )
        require(
            all(
                key in expected_cells or value == ""
                for key, value in actual.cells.items()
            ),
            "extra_content",
        )
        require(actual.merges == frozenset(table.get("merges", [])), "merge_mismatch")
    return {
        "pages": len(pages),
        "tables": len(tables),
        "cells": sum(len(row) for table in expected_tables for row in table["rows"]),
    }
