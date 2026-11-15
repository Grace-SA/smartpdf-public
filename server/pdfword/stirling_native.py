"""Opt-in native engine; page coverage and strict output validation remain mandatory."""
import ctypes
import json
import math
import os
import re
import subprocess
import time
import unicodedata
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdf
import pdfplumber
from columns import column_flow
from layout import native_page
from model import Rejected
from stirling_build import CORE_SHA256, digest
from stirling_package import normalize_package
from text_visibility import bright_text_visible
from text_geometry import glyph_geometry, ink_bounds
from text_coverage import compact, check_coverage


def has_nested_grid(page):
    """A source grid inside another grid must not silently become plain cell text."""
    grids = [table.bbox for table in page.find_tables()
             if len(table.cells) >= 4 and len(table.rows) >= 2 and len(table.columns) >= 2]
    return any(outer[0] + .5 < inner[0] and outer[1] + .5 < inner[1]
               and inner[2] < outer[2] - .5 and inner[3] < outer[3] - .5
               for outer in grids for inner in grids if outer is not inner)


def profile(source, cancel=None):
    """Rotation is supported by Java; hidden text, scans and formula content are not routed here."""
    pages = []
    from worker import clips_text
    with pdf.PdfDocument(source) as document:
        for i in range(len(document)):
            if cancel and Path(cancel).exists():
                raise Rejected("Conversion cancelled.")
            with closing(document[i]) as page, closing(page.get_textpage()) as textpage:
                geometry = glyph_geometry(textpage)
                width, height = page.get_size()
                if not all(math.isfinite(v) and 72 <= v <= 1584 for v in (width, height)):
                    return None, "page-dimensions"
                visible, objects, bright = [], 0, []
                has_images = False
                for obj in page.get_objects(max_depth=8, textpage=textpage):
                    objects += 1
                    if objects > 10000:
                        return None, "object-budget"
                    if obj.type == pdf.raw.FPDF_PAGEOBJ_IMAGE:
                        has_images = True
                        l, b, r, t = obj.get_bounds()
                        if abs((r-l)*(t-b)) > width * height * 0.60:
                            return None, "scan-or-mixed-page"
                    if obj.type != pdf.raw.FPDF_PAGEOBJ_TEXT:
                        continue
                    value = obj.extract()
                    if not value.strip():
                        continue
                    rgba = [ctypes.c_uint() for _ in range(4)]
                    ok = pdf.raw.FPDFPageObj_GetFillColor(obj, *(ctypes.byref(v) for v in rgba))
                    if (not ok or rgba[3].value != 255
                            or pdf.raw.FPDFTextObj_GetTextRenderMode(obj) in (3, 7)):
                        return None, "hidden-or-transparent-text"
                    if min(v.value for v in rgba[:3]) > 240:
                        bright.append(obj)
                    if "\ufffd" in value or any(unicodedata.category(c) in ("Co", "Cn", "Cs") for c in value):
                        return None, "unreliable-text-layer"
                    bounds = ink_bounds(obj, geometry)
                    l, b, r, t = bounds
                    crop = page.get_bbox()
                    if (clips_text(obj, bounds) or l < crop[0] - 0.5 or b < crop[1] - 0.5
                            or r > crop[2] + 0.5 or t > crop[3] + 0.5):
                        return None, "clipped-native-text"
                    if any(c in value for c in "∑∫√∂∏≠≤≥∞∈∇") or re.search(r"\\(?:frac|sqrt)\b", value):
                        return None, "formula-content"
                    visible.append(value)
                if not visible:
                    return None, "no-native-text"
                if not bright_text_visible(page, bright, geometry):
                    return None, "invisible-bright-text"
                pages.append(dict(width=width, height=height,
                                  text=textpage.get_text_range(), hasVisualContent=has_images))
    # Preserve established reading order and precise glyph-to-cell ownership where
    # the existing native reconstruction already knows the complete structure.
    with pdfplumber.open(source) as document:
        for index, page in enumerate(document.pages):
            if has_nested_grid(page):
                return None, "nested-source-grid"
            try:
                blocks = native_page(page)
            except Rejected as error:
                if str(error) == "Incomplete native table grid.":
                    page.close()
                    continue
                if str(error) == "Layout needs OCR.":
                    return None, "borderless-structured-recognition"
                raise
            pages[index]["hasVisualContent"] |= any(b["kind"] in ("image", "formula") for b in blocks)
            if any(b["kind"] == "columns_start" for b in column_flow(blocks, page.width)):
                return None, "structured-columns"
            prose = [b for b in blocks if b["kind"] in ("paragraph", "heading", "list")]
            for index, a in enumerate(prose):
                x0, y0, x1, y1 = a["bbox"]
                for b in prose[index+1:]:
                    l, t, r, bottom = b["bbox"]
                    overlap = min(y1, bottom) - max(y0, t)
                    if overlap > 0.5 * min(y1-y0, bottom-t) and (l-x1 > 24 or x0-r > 24):
                        return None, "structured-columns"
            if not page.rotation and any(b["kind"] == "table" for b in blocks):
                return None, "verified-native-grid"
            page.close()
    return pages, "native-text"


def verified_runtime():
    root = Path(os.environ["PDFWORD_STIRLING_RUNTIME"]).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if (manifest["core_sha256"] != CORE_SHA256
            or manifest["source_sha256"] != digest(Path(__file__).with_name("StirlingBridge.java"))):
        raise ValueError("Native runtime provenance mismatch")
    expected = manifest["files"]
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name != "manifest.json"}
    if actual != set(expected):
        raise ValueError("Unexpected native runtime files")
    for name, sha in expected.items():
        p = root / name
        if p.is_symlink() or not p.resolve().is_relative_to(root) or digest(p) != sha:
            raise ValueError("Native runtime hash mismatch")
    return root


def check_visual_coverage(pages, counts):
    if len(pages) != len(counts) or any(p.get("hasVisualContent") and not n for p, n in zip(pages, counts)):
        raise ValueError("Native output lost source graphics")


def convert_native(source, destination, work, pages, cancel=None, progress=None):
    runtime = verified_runtime()
    java = os.environ.get("PDFWORD_JAVA", "java")
    raw = Path(work) / "stirling-raw.docx"
    command = [java, "-Djava.awt.headless=true", "-Xmx768m", "-XX:ActiveProcessorCount=2",
               "-cp", str(runtime / "lib/*") + os.pathsep + str(runtime),
               "StirlingBridge", str(source), str(raw)]
    if progress:
        progress(dict(state="converting", completedPages=0, totalPages=len(pages), stage="reconstructing"))
    with (Path(work) / "stirling.log").open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        start = time.monotonic()
        try:
            while process.poll() is None:
                if cancel and Path(cancel).exists():
                    raise Rejected("Conversion cancelled.")
                if time.monotonic() - start > 125:
                    raise ValueError("Native engine time budget exceeded")
                time.sleep(0.1)
            if process.returncode:
                raise ValueError("Native engine failed")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    staged = Path(work) / "native-checked.docx"
    report, text = normalize_package(raw, staged, len(pages))
    report["nativeCoverage"] = check_coverage(pages, text)
    check_visual_coverage(pages, report["nativePageImages"])
    if cancel and Path(cancel).exists():
        raise Rejected("Conversion cancelled.")
    # Same independent validator used by the HTTP service, before accepting this route.
    node = os.environ.get("PDFWORD_NODE", "node")
    checker = Path(__file__).with_name("docx-check.mjs").as_uri()
    script = "import {checkDocx} from " + json.dumps(checker) + ";console.log(JSON.stringify(await checkDocx(process.argv[1])));"
    result = subprocess.run([node, "--input-type=module", "-e", script, str(staged)],
                            capture_output=True, text=True, timeout=30, check=True)
    actual = json.loads(result.stdout)
    if any(actual[k] != report[k] for k in ("images", "tables")) or actual["sourceMarkers"] != len(pages):
        raise ValueError("Native output manifest mismatch")
    if destination.exists():
        raise Rejected("Choose a new Word output file.")
    staged.rename(destination)
    report["engine"] = "stirling-office-convert-0.2.2"
    return report
