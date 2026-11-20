"""Native PDF reconstruction, bounded OCR and editable Word export."""

import argparse
import ctypes
import json
import math
import os
import tempfile
import unicodedata
from contextlib import closing
from pathlib import Path
import pdfplumber
import pypdfium2 as pdf
from pypdf import PdfReader
from model import Rejected, validate, box
from layout import native_page, repeated_margins, link_tables
from exporter import export_word
from ocr import OCR
from math_export import unsupported
from text_visibility import (bright_text_visible, cosmetic_white_rectangles,
                             fully_clipped_number, confirm_invisible_numbers,
                             exclude_invisible_numbers)
from text_geometry import repair_unmapped_glyphs, glyph_geometry, ink_bounds, mapped_bounds, repair_zero_width_blocks
from text_coverage import check_coverage, editable_block_text, editable_source_text
from native_margins import numeric_margin, upright_margin_words


def preflight(source):
    if not 0 < source.stat().st_size <= 30 * 1024**2:
        raise Rejected("Choose a PDF under 30 MiB.")
    reader = PdfReader(source, strict=True)
    if reader.is_encrypted:
        raise Rejected("Unlock the PDF before converting it.")
    if not 1 <= len(reader.pages) <= 200:
        raise Rejected("Choose a PDF with 1 to 200 pages.")
    root = reader.trailer["/Root"]
    form = root.get("/AcroForm")
    form = form.get_object() if hasattr(form, "get_object") else form
    from static_signatures import signature_widgets
    signatures = signature_widgets(reader)
    action = root.get("/OpenAction")
    action = action.get_object() if hasattr(action, "get_object") else action
    # A destination array merely sets the opening view. It is not executable content.
    if (
        any(k in root for k in ("/OCProperties", "/AA"))
        or (form and (form.get("/XFA") or (form.get("/Fields") and not signatures)))
        or (action and not isinstance(action, list))
    ):
        raise Rejected("Export a flattened PDF before converting interactive content.")
    names = root.get("/Names", {})
    if hasattr(names, "get_object"):
        names = names.get_object()
    if any(k in names for k in ("/EmbeddedFiles", "/JavaScript")):
        raise Rejected("Remove embedded files or scripts before conversion.")
    for p in reader.pages:
        if p.get("/AA"):
            raise Rejected("Interactive page actions are unsupported.")
        for ref in p.get("/Annots", []):
            if ref.get_object().get("/Subtype") != "/Link" and id(ref.get_object()) not in signatures:
                raise Rejected("Flatten visible annotations before conversion.")
    return len(reader.pages)


def clips_text(obj, bounds=None):
    clip = pdf.raw.FPDFPageObj_GetClipPath(obj)
    for i in range(pdf.raw.FPDFClipPath_CountPaths(clip)):
        count = pdf.raw.FPDFClipPath_CountPathSegments(clip, i)
        if count not in (4, 5):
            return True
        points = []
        for j in range(count):
            segment = pdf.raw.FPDFClipPath_GetPathSegment(clip, i, j)
            if pdf.raw.FPDFPathSegment_GetType(segment) not in (0, 2):
                return True
            x, y = ctypes.c_float(), ctypes.c_float()
            if not pdf.raw.FPDFPathSegment_GetPoint(
                segment, ctypes.byref(x), ctypes.byref(y)
            ):
                return True
            points.append((round(x.value, 3), round(y.value, 3)))
        xs = {p[0] for p in points}
        ys = {p[1] for p in points}
        if len(xs) != 2 or len(ys) != 2 or len(set(points)) != 4:
            return True
        if any(
            a[0] != b[0] and a[1] != b[1]
            for a, b in zip(points, points[1:] + points[:1])
        ):
            return True
        l, b, r, t = bounds if bounds is not None else obj.get_bounds()
        if (
            l < min(xs) - 0.5
            or r > max(xs) + 0.5
            or b < min(ys) - 0.5
            or t > max(ys) + 0.5
        ):
            return True
    return False


def needs_ocr(page, rotated_cells=()):
    visible = 0
    images = 0
    unsafe = False
    bright = []
    clipped_numbers = []
    with closing(page.get_textpage()) as tp:
        geometry = glyph_geometry(tp)
        from invisible_margins import proven_margin_objects
        from text_geometry import handle
        invisible_margins = {handle(obj) for obj in proven_margin_objects(page, tp)}
        objects = 0
        for obj in page.get_objects(max_depth=8, textpage=tp):
            objects += 1
            if objects > 10000:
                raise Rejected("Page exceeds object limit.")
            if obj.type == pdf.raw.FPDF_PAGEOBJ_IMAGE:
                images += 1
            if obj.type != pdf.raw.FPDF_PAGEOBJ_TEXT:
                continue
            if handle(obj) in invisible_margins:
                continue
            value = obj.extract()
            if not value.strip():
                continue
            mapped = mapped_bounds(obj, geometry)
            crop = page.get_bbox()
            # Completely off-page text is not visible content. Ignore it only
            # when every non-space glyph has an independently mapped box; the
            # native extractor below is cropped to the same visible page.
            if mapped and (mapped[2] <= crop[0] or mapped[0] >= crop[2]
                           or mapped[3] <= crop[1] or mapped[1] >= crop[3]):
                continue
            if fully_clipped_number(obj, geometry):
                clipped_numbers.append(obj)
                continue
            rgba = [ctypes.c_uint() for _ in range(4)]
            ok = pdf.raw.FPDFPageObj_GetFillColor(obj, *(ctypes.byref(v) for v in rgba))
            mode = pdf.raw.FPDFTextObj_GetTextRenderMode(obj)
            if mode in (3, 7):
                unsafe = True
                continue
            visible += len(value)
            unsafe |= (
                not ok
                or rgba[3].value != 255
                or "\ufffd" in value
            )
            if min(v.value for v in rgba[:3]) > 240:
                bright.append(obj)
            unsafe |= any(unicodedata.category(c) in ("Co", "Cn", "Cs") for c in value)
            bounds = ink_bounds(obj, geometry)
            unsafe |= clips_text(obj, bounds)
            l, b, r, t = bounds
            unsafe |= (
                l < crop[0] - 0.5
                or b < crop[1] - 0.5
                or r > crop[2] + 0.5
                or t > crop[3] + 0.5
            )
            matrix = obj.get_matrix()
            orthogonal_cell = (abs(matrix.a) < .001 and abs(matrix.d) < .001
                and matrix.b*matrix.c < 0 and any(
                    bounds[0] >= cell[0]-.5 and bounds[1] >= cell[1]-.5
                    and bounds[2] <= cell[2]+.5 and bounds[3] <= cell[3]+.5
                    for cell in rotated_cells))
            unsafe |= not orthogonal_cell and not numeric_margin(obj, page, geometry) and (
                abs(matrix.b) > 0.001
                or abs(matrix.c) > 0.001
                or matrix.a <= 0
                or matrix.d <= 0
            )
        unsafe |= not bright_text_visible(page, bright, geometry)
        unsafe |= not confirm_invisible_numbers(page, clipped_numbers)
    return (
        (not visible and bool(images)) or unsafe or bool(page.get_rotation()),
        visible,
        images,
    )


def raster_scale(page):
    width, height = page.get_size()
    return min(2.5, math.sqrt(16000000 / (width * height)))


def render(page, path):
    scale = raster_scale(page)
    with closing(page.render(scale=scale)) as bitmap:
        bitmap.to_pil().convert("RGB").save(path)


def checked_native_page(page, native, visible, cosmetic=(), proposals=()):
    """All native candidates pass the same visibility-independent output gates."""
    blocks = native_page(native, cosmetic, proposals)
    expected = editable_source_text(native, blocks)
    width, height = page.get_size()
    left, _, _, top = page.get_bbox()
    offset_top = native.root_page.height-top
    if left or offset_top:
        for block in blocks:
            block['bbox'] = [v-(left if n % 2 == 0 else offset_top)
                             for n, v in enumerate(block['bbox'])]
    repair_zero_width_blocks(page, blocks)
    try:
        for block in blocks:
            box(block['bbox'], width, height)
    except Rejected as error:
        raise Rejected("Layout needs OCR.") from error
    if (not visible and blocks) or any(
            b['kind'] == 'image' and (b['bbox'][2]-b['bbox'][0])*(b['bbox'][3]-b['bbox'][1])
            > width*height*.65 for b in blocks):
        raise Rejected("Layout needs OCR.")
    try:
        check_coverage([{'text': expected}], [editable_block_text(blocks)], numeric_tokens=False)
    except ValueError as error:
        raise Rejected("Layout needs OCR.") from error
    return blocks


def parse_pdf(source, work, ocr=None, progress=None, cancel=None):
    source = Path(source)
    work = Path(work)
    count = preflight(source)
    model = dict(schema=2, pages=[], warnings=[])
    from static_signatures import flatten_signatures, NOTICE
    source, static_signature = flatten_signatures(source, work)
    if static_signature:
        model["warnings"].append(NOTICE)
    from native_orientation import normalize_orientation
    source, corrected = normalize_orientation(source, work, cancel)
    for index in corrected:
        model["warnings"].append(f"Page {index+1}: native text direction was corrected; check page orientation.")
    pixels = 0
    from stream_tables import StreamTables
    stream_tables = StreamTables(source)
    with pdf.PdfDocument(source) as doc, pdfplumber.open(source) as textdoc:
        if len(doc) != count or len(textdoc.pages) != count:
            raise Rejected("PDF page structure needs review.")
        for i in range(count):
            if cancel and Path(cancel).exists():
                raise Rejected("Conversion cancelled.")
            with closing(doc[i]) as page:
                width, height = page.get_size()
                if not all(
                    math.isfinite(v) and 72 <= v <= 1584 for v in (width, height)
                ):
                    raise Rejected("Unsupported page dimensions.")
                use_ocr, visible, images = needs_ocr(page)
                if use_ocr and not page.get_rotation():
                    candidate = textdoc.pages[i]
                    if any(not c.get('upright', True) for c in candidate.chars):
                        from ruled_tables import reconstruct
                        try:
                            grids = reconstruct(candidate, candidate.extract_words(return_chars=True)) or []
                            regions = [[c['bbox'][0], candidate.height-c['bbox'][3],
                                        c['bbox'][2], candidate.height-c['bbox'][1]]
                                       for grid in grids for c in grid['cells'] if c.get('direction')]
                            if regions:
                                use_ocr, visible, images = needs_ocr(page, regions)
                        except Rejected:
                            pass
                native_text_safe = not use_ocr
                full = work / f"page-{i}.png"
                blocks = []
                if not use_ocr:
                    p = textdoc.pages[i]
                    l, b, r, t = page.get_bbox()
                    top = p.height - t
                    if not page.get_rotation():
                        # PDFium uses floats while pdfplumber retains PDF decimal
                        # coordinates; their page edges can differ by micrometres.
                        p = p.crop((l, top, r, top + height), strict=False)
                    p = repair_unmapped_glyphs(page, p)
                    p = exclude_invisible_numbers(page, p)
                    if p is not None:
                        from invisible_margins import exclude_margin_text
                        p = exclude_margin_text(page, p)
                    if p is not None:
                        p = upright_margin_words(page, p)
                    use_ocr = True
                    if p is not None:
                        cosmetic = cosmetic_white_rectangles(page)
                        for attempt in range(2):
                            proposals = stream_tables.proposals(i) if attempt else ()
                            if attempt and not proposals:
                                break
                            try:
                                blocks = checked_native_page(page, p, visible, cosmetic, proposals)
                                use_ocr = False
                                break
                            except Rejected as error:
                                if str(error) not in ("Incomplete native table grid.", "Layout needs OCR."):
                                    raise
                if use_ocr:
                    scale = raster_scale(page)
                    pixels += math.ceil(width * scale) * math.ceil(height * scale)
                    if pixels > max(256000000, count * 4000000):
                        raise Rejected(
                            "OCR page pixels exceed the task budget. Split the document."
                        )
                    render(page, full)
                    if progress:
                        progress(
                            dict(
                                state="converting",
                                completedPages=i,
                                totalPages=count,
                                stage="recognizing",
                            )
                        )
                    if ocr is None:
                        raise Rejected(
                            "This PDF needs OCR. The OCR worker is not configured."
                        )
                    blocks = ocr.recognize(
                        full, width, height, complex_layout=bool(visible)
                    )
                    corrected_size = getattr(ocr, "last_page_size", None)
                    if isinstance(corrected_size, (tuple, list)):
                        if len(corrected_size) != 2 or any(
                            type(v) not in (int, float) or not math.isfinite(v)
                            or not 72 <= v <= 1584 for v in corrected_size
                        ):
                            raise Rejected("Invalid corrected page geometry.")
                        # Regions and retained image crops now use the upright
                        # OCR canvas; Word must use the same physical page size.
                        width, height = corrected_size
                    if getattr(ocr, "last_engine", None) == "u2-fallback":
                        model["warnings"].append(
                            f"Page {i+1}: alternative OCR recovered an incomplete result; review the page."
                        )
                    if native_text_safe and getattr(ocr, 'last_native_coordinates', False):
                        from native_ocr_text import reconcile
                        safe_native = exclude_invisible_numbers(page, textdoc.pages[i])
                        if safe_native is not None:
                            from invisible_margins import exclude_margin_text
                            safe_native = exclude_margin_text(page, safe_native)
                        restored = reconcile(page, safe_native, blocks) if safe_native is not None else 0
                        if restored:
                            model['warnings'].append(f'Page {i+1}: independently verified native text restored in {restored} OCR regions.')
                    if not blocks:
                        raise Rejected(f"Page {i+1} produced no recognized content.")
                    model["warnings"].append(
                        f"Page {i+1}: text was recognized with OCR; check names and numbers."
                    )
                for j, block in enumerate(blocks):
                    if block.get("ocr_orientation_review"):
                        model["warnings"].append(
                            f"Page {i+1}: uncertain OCR rotation was not applied; check the page direction."
                        )
                    if block.get("ocr_overlap_review"):
                        model["warnings"].append(
                            f"Page {i+1}: overlapping OCR readings differ; check repeated text against the source."
                        )
                    block["bbox"] = box(block["bbox"], width, height)
                    block["id"] = f"p{i}-b{j}"
                    block["reading_order"] = j
                    if unsupported(block.get("text", "")):
                        model["warnings"].append(
                            f"Page {i+1}: inline formula markup needs manual formatting."
                        )
                    if block["kind"] in ("image", "formula"):
                        if not full.exists():
                            render(page, full)
                        from PIL import Image

                        with Image.open(full) as image:
                            x0, y0, x1, y1 = block["bbox"]
                            sx = image.width / width
                            sy = image.height / height
                            region = image.crop(
                                (
                                    int(x0 * sx),
                                    int(y0 * sy),
                                    math.ceil(x1 * sx),
                                    math.ceil(y1 * sy),
                                )
                            )
                            asset = f"p{i}-b{j}.png"
                            region.save(work / asset)
                            block["asset"] = asset
                        if block["kind"] == "formula":
                            model["warnings"].append(
                                f"Page {i+1}: a formula is retained as an image."
                            )
                model["pages"].append(
                    dict(
                        index=i,
                        width=width,
                        height=height,
                        rotation=page.get_rotation(),
                        blocks=blocks,
                    )
                )
                if progress:
                    progress(
                        dict(
                            state="converting",
                            completedPages=i + 1,
                            totalPages=count,
                            stage="reconstructing",
                        )
                    )
                # Retained figure/formula crops have separate asset files.
                # Release full page rasters before processing the next page.
                full.unlink(missing_ok=True)
                textdoc.pages[i].close()
    repeated_margins(model["pages"])
    link_tables(model["pages"])
    if not any(
        b.get("text") or b["kind"] == "table"
        for p in model["pages"]
        for b in p["blocks"]
    ):
        raise Rejected("No editable text was found. Try a clearer scan.")
    model["warnings"] = list(dict.fromkeys(model["warnings"]))
    return validate(model)


def convert(source, destination, *, engine=None, cancel=None, progress=None):
    source = Path(source)
    destination = Path(destination)
    if destination.exists():
        raise Rejected("Choose a new Word output file.")
    preflight(source)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        from static_signatures import flatten_signatures, NOTICE
        source, static_signature = flatten_signatures(source, temp)
        native_reason = "disabled"
        if os.environ.get("PDFWORD_NATIVE_ENGINE") == "stirling":
            from stirling_native import profile, convert_native

            try:
                pages, native_reason = profile(source, cancel=cancel)
            except Exception as error:
                if cancel and Path(cancel).exists():
                    raise Rejected("Conversion cancelled.") from error
                pages, native_reason = None, "native-profile-fallback:" + type(error).__name__
            if pages:
                try:
                    report = convert_native(source, destination, temp, pages, cancel, progress)
                    if static_signature:
                        report["warnings"].append(NOTICE)
                    return report
                except Rejected:
                    raise
                except Exception as error:
                    # Keep the final file absent until a complete route has passed validation.
                    native_reason = "native-fallback:" + type(error).__name__ + ":" + str(error)[:160]
        ocr = OCR(temp, cancel=cancel, engine=engine)
        try:
            model = parse_pdf(
                source,
                temp,
                ocr=ocr,
                progress=progress,
                cancel=cancel,
            )
        finally:
            ocr.close()
        if cancel and Path(cancel).exists():
            raise Rejected("Conversion cancelled.")
        report = export_word(model, destination, temp)
        report["engine"] = "structured-ocr" if any("OCR" in v for v in model["warnings"]) else "structured-native"
        report["nativeRoute"] = native_reason
        if static_signature:
            report["warnings"].append(NOTICE)
        return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--engine", choices=["auto", "u2", "oxr", "paddle"])
    p.add_argument("--cancel", type=Path)
    args = p.parse_args()
    try:
        print(
            json.dumps(
                convert(
                    args.source,
                    args.destination,
                    engine=args.engine,
                    cancel=args.cancel,
                )
            )
        )
    except Rejected as error:
        print(json.dumps(dict(error=str(error), code="INPUT_REJECTED")))
        raise SystemExit(2)
    except Exception:
        print(
            json.dumps(
                dict(
                    error="The PDF could not be converted safely.",
                    code="CONVERSION_FAILED",
                )
            )
        )
        raise SystemExit(3)
