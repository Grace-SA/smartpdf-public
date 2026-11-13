"""Native PDF reconstruction, bounded OCR and editable Word export."""

import argparse
import ctypes
import json
import math
import tempfile
import unicodedata
from contextlib import closing
from pathlib import Path
import pdfplumber
import pypdfium2 as pdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NullObject
from model import Rejected, validate, box
from layout import native_page, repeated_margins, link_tables
from exporter import export_word
from ocr import OCR
from math_export import unsupported


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
    action = root.get("/OpenAction")
    action = action.get_object() if hasattr(action, "get_object") else action
    # A destination array merely sets the opening view. It is not executable content.
    if (
        any(k in root for k in ("/OCProperties", "/AA"))
        or (form and (form.get("/Fields") or form.get("/XFA")))
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
            if ref.get_object().get("/Subtype") != "/Link":
                raise Rejected("Flatten visible annotations before conversion.")
    return len(reader.pages)


def clips_text(obj):
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
        l, b, r, t = obj.get_bounds()
        if (
            l < min(xs) - 0.5
            or r > max(xs) + 0.5
            or b < min(ys) - 0.5
            or t > max(ys) + 0.5
        ):
            return True
    return False


def needs_ocr(page):
    visible = 0
    images = 0
    unsafe = False
    with closing(page.get_textpage()) as tp:
        objects = 0
        for obj in page.get_objects(max_depth=8, textpage=tp):
            objects += 1
            if objects > 10000:
                raise Rejected("Page exceeds object limit.")
            if obj.type == pdf.raw.FPDF_PAGEOBJ_IMAGE:
                images += 1
            if obj.type != pdf.raw.FPDF_PAGEOBJ_TEXT:
                continue
            value = obj.extract()
            if not value.strip():
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
                or min(v.value for v in rgba[:3]) > 240
                or "\ufffd" in value
            )
            unsafe |= any(unicodedata.category(c) in ("Co", "Cn", "Cs") for c in value)
            unsafe |= clips_text(obj)
            l, b, r, t = obj.get_bounds()
            crop = page.get_bbox()
            unsafe |= (
                l < crop[0] - 0.5
                or b < crop[1] - 0.5
                or r > crop[2] + 0.5
                or t > crop[3] + 0.5
            )
            matrix = obj.get_matrix()
            unsafe |= (
                abs(matrix.b) > 0.001
                or abs(matrix.c) > 0.001
                or matrix.a <= 0
                or matrix.d <= 0
            )
    return (
        (not visible and bool(images)) or unsafe or bool(page.get_rotation()),
        visible,
        images,
    )


def raster_regions_need_ocr(blocks, width, height):
    """Count collective raster coverage, without double-counting overlap.

    A native title must not make a tiled scan silently remain image-only. Bound
    the geometry work and use the guarded recognition path for excessive regions.
    """
    boxes = [[max(0, min(width, b["bbox"][0])), max(0, min(height, b["bbox"][1])),
              max(0, min(width, b["bbox"][2])), max(0, min(height, b["bbox"][3]))]
             for b in blocks if b["kind"] == "image"]
    boxes = [b for b in boxes if b[0] < b[2] and b[1] < b[3]]
    if len(boxes) > 512:
        return True
    xs = sorted({x for b in boxes for x in (max(0, b[0]), min(width, b[2]))})
    area = 0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted((max(0, b[1]), min(height, b[3]))
                           for b in boxes if b[0] < right and b[2] > left)
        covered = 0
        end = 0
        for top, bottom in intervals:
            covered += max(0, bottom - max(top, end))
            end = max(end, bottom)
        area += (right - left) * covered
        if area > width * height * 0.65:
            return True
    return False


def raster_scale(page):
    width, height = page.get_size()
    return min(2.5, math.sqrt(16000000 / (width * height)))


def render(page, path):
    scale = raster_scale(page)
    with closing(page.render(scale=scale)) as bitmap:
        bitmap.to_pil().convert("RGB").save(path)


def normalize_page_rotations(source, work, cancel=None):
    """Flatten page-view rotation, not visible text orientation, before geometry.

    Some producers encode upright landscape/portrait text as inverse content
    rotation plus /Rotate. Such pages need no recognition. Visible side-on text
    remains rotated after this operation and still takes the guarded OCR path.
    Call only after original-source preflight; never rewrite the user's input.
    """
    reader = PdfReader(source, strict=True)
    rotations = [page.rotation for page in reader.pages]
    if any(rotation % 90 or not -(2**31) <= rotation < 2**31 for rotation in rotations):
        raise Rejected("Unsupported page rotation.")
    # pypdf transforms page content/boxes, not annotation appearance geometry.
    # Preserve annotated pages verbatim so visible link borders cannot move.
    rotations = [0 if page.get("/Annots") else rotation for page, rotation in zip(reader.pages, rotations)]
    if not any(rotation % 360 for rotation in rotations):
        return source
    writer = PdfWriter()
    expanded_bytes = 0
    for page, rotation in zip(reader.pages, rotations):
        if cancel and Path(cancel).exists():
            raise Rejected("Conversion cancelled.")
        if rotation % 360:
            # Bound expanded page instructions before pypdf parses/copies them.
            # Image/font streams are not expanded by this normalization step.
            contents = page.get("/Contents")
            contents = contents.get_object() if contents is not None else []
            streams = contents if isinstance(contents, list) else [contents]
            page_bytes = 0
            for stream in streams:
                stream = stream.get_object()
                if isinstance(stream, NullObject):
                    continue
                page_bytes += len(stream.get_data())
                if page_bytes > 8 * 1024**2:
                    raise Rejected("Rotated page instructions exceed the task budget.")
            expanded_bytes += page_bytes
            if expanded_bytes > 64 * 1024**2:
                raise Rejected("Rotated document instructions exceed the task budget.")
        cloned = writer.add_page(page)
        if rotation % 360:
            cloned.rotation = rotation % 360
            cloned.transfer_rotation_to_content()
            cloned.compress_content_streams(level=1)
    with tempfile.NamedTemporaryFile(prefix="rotation-", suffix=".pdf", dir=work, delete=False) as output:
        result = Path(output.name)
        try:
            writer.write(output)
        except BaseException:
            result.unlink(missing_ok=True)
            raise
    if result.stat().st_size > 60 * 1024**2:
        result.unlink(missing_ok=True)
        raise Rejected("Normalized PDF exceeds the task budget.")
    return result


def parse_pdf(source, work, ocr=None, progress=None, cancel=None):
    source = Path(source)
    work = Path(work)
    count = preflight(source)
    source = normalize_page_rotations(source, work, cancel)
    model = dict(schema=2, pages=[], warnings=[])
    pixels = 0
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
                full = work / f"page-{i}.png"
                blocks = []
                if not use_ocr:
                    p = textdoc.pages[i]
                    l, b, r, t = page.get_bbox()
                    top = p.height - t
                    if not page.get_rotation() and (
                        abs(width - p.width) > 1 or abs(height - p.height) > 1
                    ):
                        p = p.crop((l, top, r, top + height))
                    try:
                        blocks = native_page(p)
                    except Rejected as error:
                        if str(error) not in (
                            "Incomplete native table grid.",
                            "Layout needs OCR.",
                        ):
                            raise
                        use_ocr = True
                    if l or top:
                        for block in blocks:
                            block["bbox"] = [
                                v - (l if n % 2 == 0 else top)
                                for n, v in enumerate(block["bbox"])
                            ]
                    use_ocr = use_ocr or raster_regions_need_ocr(blocks, width, height)
                    # Outlined glyphs and image-only regions must be recognized, not silently omitted.
                    use_ocr = use_ocr or (not visible and bool(blocks))
                if use_ocr:
                    scale = raster_scale(page)
                    pixels += math.ceil(width * scale) * math.ceil(height * scale)
                    if pixels > 256000000:
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
                    if getattr(ocr, "last_engine", None) == "u2-fallback":
                        model["warnings"].append(
                            f"Page {i+1}: alternative OCR recovered an incomplete result; review the page."
                        )
                    if not blocks:
                        raise Rejected(f"Page {i+1} produced no recognized content.")
                    model["warnings"].append(
                        f"Page {i+1}: text was recognized with OCR; check names and numbers."
                    )
                for j, block in enumerate(blocks):
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
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
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
        return export_word(model, destination, temp)


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

