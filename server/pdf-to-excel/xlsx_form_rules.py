"""Attach bounded source separator lines to their actual workbook coordinates."""

from collections import defaultdict
from pathlib import Path
from bisect import bisect_right
import math
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from openpyxl.drawing.spreadsheet_drawing import (
    SpreadsheetDrawing,
    TwoCellAnchor,
    AnchorMarker,
)
from openpyxl.drawing.connector import Shape, ShapeMeta
from openpyxl.drawing.properties import (
    NonVisualDrawingProps,
    NonVisualDrawingShapeProps,
)
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.geometry import PresetGeometry2D
from openpyxl.drawing.line import LineProperties
from openpyxl.xml.functions import tostring

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def attach(path, tables, placements=None):
    """placements contains (one-based sheet index, zero-based starting row)."""
    path = Path(path)
    if placements is None:
        placements = [(i, 0) for i in range(1, len(tables) + 1)]
    if len(tables) != len(placements):
        raise ValueError("Invalid source drawing placements")
    grouped = defaultdict(list)
    for table, (sheet, offset) in zip(tables, placements):
        rules = table.get("sourceRules", [])
        if not rules:
            continue
        if (
            type(sheet) is not int
            or type(offset) is not int
            or not 1 <= sheet <= 1000
            or offset < 0
        ):
            raise ValueError("Invalid source drawing placement")
        ys = table.get("sourceRowEdges", [])
        widths = table.get("widths", [])
        if (
            len(rules) > 64
            or not widths
            or len(ys) < 2
            or offset + len(ys) - 1 > 1048576
            or len(widths) > 16384
            or any(
                not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in widths + ys
            )
            or any(w <= 0 for w in widths)
            or any(b <= a for a, b in zip(ys, ys[1:]))
        ):
            raise ValueError("Invalid source drawing geometry")
        if max(widths) - min(widths) > 1e-6:
            raise ValueError("Source drawing requires a uniform coordinate grid")
        for rule in rules:
            if (
                any(
                    not isinstance(rule.get(k), (int, float))
                    or not math.isfinite(rule[k])
                    for k in ["x0", "x1", "y", "weight"]
                )
                or not 0 <= rule["x0"] < rule["x1"] <= sum(widths)
                or not ys[0] <= rule["y"] < ys[-1]
                or not 0 < rule["weight"] <= 4
            ):
                raise ValueError("Invalid source rule")
        grouped[sheet].append((table, offset))
    if sum(len(v) for v in grouped.values()) > 200:
        raise ValueError("Too many source form pages")
    if not grouped:
        return
    with ZipFile(path) as z:
        members = {n: z.read(n) for n in z.namelist()}
    types = ET.fromstring(members["[Content_Types].xml"])
    for index, entries in grouped.items():
        drawing = SpreadsheetDrawing()
        unit = entries[0][0]["widths"][0]
        for table, offset in entries:
            if abs(table["widths"][0] - unit) > 1e-6:
                raise ValueError("Inconsistent source coordinate grid")
            ys = table["sourceRowEdges"]
            for rule in table["sourceRules"]:
                row = bisect_right(ys, rule["y"]) - 1
                row_offset = round((rule["y"] - ys[row]) * 12700)

                def marker(x):
                    col = math.floor(x / unit)
                    return AnchorMarker(
                        col=col,
                        colOff=round((x - col * unit) * 12700),
                        row=offset + row,
                        rowOff=row_offset,
                    )

                identifier = len(drawing.twoCellAnchor) + 1
                shape_props = NonVisualDrawingShapeProps()
                # openpyxl 3.1.5 serializes txBax but initializes txBox. Leave
                # the optional attribute absent rather than emitting a Bool object.
                shape_props.txBax = None
                shape = Shape(
                    nvSpPr=ShapeMeta(
                        cNvPr=NonVisualDrawingProps(
                            id=identifier, name=f"Source separator {identifier}"
                        ),
                        cNvSpPr=shape_props,
                    ),
                    spPr=GraphicalProperties(
                        prstGeom=PresetGeometry2D(prst="line"),
                        ln=LineProperties(
                            w=max(1270, round(rule["weight"] * 12700)),
                            solidFill="000000",
                            prstDash="solid",
                        ),
                    ),
                )
                drawing.twoCellAnchor.append(
                    TwoCellAnchor(
                        _from=marker(rule["x0"]),
                        to=marker(rule["x1"]),
                        sp=shape,
                        editAs="twoCell",
                    )
                )
        name = f"xl/drawings/form-rules-{index}.xml"
        sheetname = f"xl/worksheets/sheet{index}.xml"
        sheet = ET.fromstring(members[sheetname])
        relname = f"xl/worksheets/_rels/sheet{index}.xml.rels"
        rels = (
            ET.fromstring(members[relname])
            if relname in members
            else ET.Element(f"{{{PKG}}}Relationships")
        )
        if (
            name in members
            or sheet.find(f"{{{NS}}}drawing") is not None
            or any(r.get("Id") == "rIdFormRules" for r in rels)
        ):
            raise ValueError("Existing drawing or relationship must not be replaced")
        members[name] = tostring(drawing._write())
        # CT_Worksheet orders drawing before legacyDrawing (comment VML),
        # tableParts and the other trailing worksheet elements. Appending here
        # produces invalid order when a shared sheet already contains comments.
        element = ET.Element(f"{{{NS}}}drawing", {f"{{{REL}}}id": "rIdFormRules"})
        following = {
            f"{{{NS}}}{name}"
            for name in (
                "legacyDrawing", "legacyDrawingHF", "picture", "oleObjects",
                "controls", "webPublishItems", "tableParts", "extLst",
            )
        }
        position = next(
            (i for i, child in enumerate(sheet) if child.tag in following), len(sheet)
        )
        sheet.insert(position, element)
        members[sheetname] = ET.tostring(sheet)
        ET.SubElement(
            rels,
            f"{{{PKG}}}Relationship",
            {
                "Id": "rIdFormRules",
                "Type": REL + "/drawing",
                "Target": f"../drawings/form-rules-{index}.xml",
            },
        )
        members[relname] = ET.tostring(rels)
        ET.SubElement(
            types,
            f"{{{CT}}}Override",
            {
                "PartName": "/" + name,
                "ContentType": "application/vnd.openxmlformats-officedocument.drawing+xml",
            },
        )
    members["[Content_Types].xml"] = ET.tostring(types)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=path.name + ".rules.", suffix=".tmp", delete=False
    ) as handle:
        temp = Path(handle.name)
    try:
        with ZipFile(temp, "w", ZIP_DEFLATED) as z:
            for name, content in members.items():
                z.writestr(name, content)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
