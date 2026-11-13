"""Recognize a narrow full-page scan with an entirely Tr=3 text layer.

This is content-stream evidence, not a general visibility detector. White text,
alpha, occlusion, clipping and arbitrary mixed pages are not inferred.
Only bounded, non-nested, text-only Forms with identity Matrix are supported.
``other`` means a supported stream did not satisfy the rule; ``unsupported``
means it could not be proved. Neither result authorizes discarding native text.
"""

import base64
import math
import zlib
from numbers import Real

from pypdf.errors import PyPdfError
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    EncodedStreamObject,
    NameObject,
    TextStringObject,
)

MAX_STREAMS = 32
MAX_BYTES = 2 * 1024 * 1024
MAX_OPS = 20000
MAX_STACK = 64
MAX_RESOURCES = 256
MAX_FORMS = 8
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class Unsupported(ValueError):
    pass


def resolve(value):
    return value.get_object() if hasattr(value, "get_object") else value


def numbers(args, count):
    if len(args) != count or any(
        isinstance(v, bool)
        or not isinstance(v, Real)
        or not math.isfinite(v)
        or abs(v) > 10_000_000
        for v in args
    ):
        raise Unsupported("Malformed numeric operands")
    return tuple(float(v) for v in args)


def resource(resources, category, name):
    if not isinstance(name, NameObject):
        raise Unsupported("Invalid resource name")
    mapping = resolve(resources.get(category, DictionaryObject()))
    if not isinstance(mapping, DictionaryObject) or len(mapping) > MAX_RESOURCES:
        raise Unsupported("Unsupported resource dictionary")
    obj = resolve(mapping.get(name))
    if not isinstance(obj, DictionaryObject):
        raise Unsupported("Missing resource")
    return obj


def bounded_content(stream, remaining):
    """Decode only standard bounded content, without pypdf's decoded cache.

    The installed pypdf stores PDF-reader stream bytes in `_data`. Calling
    get_data() first would inflate and cache the entire stream before our cap.
    Unsupported filters/parameters decline this optional classifier instead.
    """
    if type(stream) not in (DecodedStreamObject, EncodedStreamObject):
        raise Unsupported("Unsupported content stream type")
    if any(k in stream for k in ("/DecodeParms", "/F", "/FFilter", "/FDecodeParms")):
        raise Unsupported("Content parameters or external streams unsupported")
    data = stream._data
    if not isinstance(data, bytes) or remaining < 0 or len(data) > remaining:
        raise Unsupported("Content byte budget")
    filters = resolve(stream.get("/Filter"))
    if filters is None:
        return data
    if isinstance(filters, NameObject):
        filters = [filters]
    elif isinstance(filters, ArrayObject):
        filters = list(filters)
    else:
        raise Unsupported("Invalid content filters")
    if not 1 <= len(filters) <= 2:
        raise Unsupported("Content filter budget")
    for item in filters:
        name = resolve(item)
        if not isinstance(name, NameObject):
            raise Unsupported("Invalid content filter")
        try:
            if name in ("/FlateDecode", "/Fl"):
                decoder = zlib.decompressobj()
                data = decoder.decompress(data, remaining + 1)
                if (
                    len(data) > remaining
                    or not decoder.eof
                    or decoder.unused_data
                    or decoder.unconsumed_tail
                ):
                    raise Unsupported("Incomplete, trailing or oversized Flate data")
            elif name in ("/ASCII85Decode", "/A85"):
                # A single 'z' expands to four bytes. This conservative bound
                # also covers ordinary groups and whitespace without predecode.
                if len(data) > remaining // 4:
                    raise Unsupported("ASCII85 expansion budget")
                data = base64.a85decode(data, adobe=True)
            else:
                raise Unsupported("Unsupported content filter")
        except (zlib.error, ValueError) as exc:
            raise Unsupported("Invalid or unsupported content encoding") from exc
        if len(data) > remaining:
            raise Unsupported("Decoded content byte budget")
    return data


def classify(page):
    """Return 'hidden', 'other', or 'unsupported' for one pypdf page.

    Call on the same prepared PDF used by conversion. The caller must bypass
    *all* native extraction for 'hidden' pages and either OCR or explicitly
    reject them. No mutation, rendering, model calls or network access occurs.
    """
    try:
        return _classify(page)
    except (
        PyPdfError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        RecursionError,
        OSError,
    ):
        # PDF dictionaries/streams are untrusted; malformed optional evidence
        # must never make a page look like a proven hidden-text scan.
        return "unsupported"


def _classify(page):
    if page.get("/Rotate", 0) != 0 or page.get("/UserUnit", 1) != 1:
        return "unsupported"
    if page.get("/Annots"):
        return "unsupported"
    view = numbers(tuple(page.cropbox), 4)
    if view[2] <= view[0] or view[3] <= view[1]:
        return "unsupported"
    resources = resolve(page.get("/Resources"))
    if not isinstance(resources, DictionaryObject) or len(resources) > MAX_RESOURCES:
        return "unsupported"
    # All invoked streams share budgets, including repeated Form invocations.
    budget = {"bytes": 0, "streams": 0, "ops": 0, "forms": 0}
    raw = resolve(page.get("/Contents"))
    streams = list(raw) if isinstance(raw, ArrayObject) else [raw]
    operations = read_operations(streams, page.pdf, budget)
    images, modes = interpret(operations, resources, page.pdf, budget)
    if len(images) != 1 or not modes or any(mode != 3 for mode in modes):
        return "other"
    box = images[0]
    return "hidden" if all(abs(a - b) <= 0.01 for a, b in zip(box, view)) else "other"


def read_operations(streams, pdf, budget):
    """Concatenate page streams without resetting state; budget Forms too."""
    if len(streams) > MAX_STREAMS - budget["streams"]:
        raise Unsupported("Content stream budget")
    budget["streams"] += len(streams)
    pieces = []
    for stream in streams:
        data = bounded_content(resolve(stream), MAX_BYTES - budget["bytes"] - 1)
        budget["bytes"] += len(data) + 1
        pieces.append(data)
    decoded = DecodedStreamObject()
    decoded.set_data(b"\n".join(pieces))
    operations = ContentStream(decoded, pdf).operations
    budget["ops"] += len(operations)
    if budget["ops"] > MAX_OPS:
        raise Unsupported("Content operator budget")
    return operations


def form_resources(obj):
    # Unknown dictionary entries can introduce reference XObjects, optional
    # content or transparency behavior. Decline instead of ignoring them.
    allowed = {
        "/Type",
        "/Subtype",
        "/FormType",
        "/BBox",
        "/Matrix",
        "/Resources",
        "/Length",
        "/Filter",
    }
    if obj.get("/Type", "/XObject") != "/XObject":
        raise Unsupported("Invalid Form object type")
    if set(obj) - allowed:
        raise Unsupported("Unsupported Form attributes")
    (form_type,) = numbers([obj.get("/FormType", 1)], 1)
    if form_type != 1:
        raise Unsupported("Unsupported Form type")
    box = numbers(resolve(obj.get("/BBox")), 4)
    if box[2] <= box[0] or box[3] <= box[1]:
        raise Unsupported("Invalid Form bounding box")
    matrix = numbers(resolve(obj.get("/Matrix", IDENTITY)), 6)
    if matrix != IDENTITY:
        raise Unsupported("Non-identity Form Matrix")
    resources = resolve(obj.get("/Resources"))
    if not isinstance(resources, DictionaryObject) or len(resources) > MAX_RESOURCES:
        raise Unsupported("Explicit Form resources required")
    return resources


def interpret(
    operations,
    resources,
    pdf,
    budget,
    matrix=IDENTITY,
    mode=0,
    font=None,
    form=False,
    stack_base=0,
):
    # Font is the resolved font object, not its resource name: an inherited
    # font stays bound to the parent's object despite Form resource shadowing.
    in_text = False
    stack, images, modes = [], [], []
    for args, op in operations:
        if op == b"q":
            numbers(args, 0)
            if stack_base + len(stack) >= MAX_STACK:
                raise Unsupported("Graphics stack budget")
            stack.append((matrix, mode, font))
        elif op == b"Q":
            numbers(args, 0)
            if not stack:
                raise Unsupported("Unbalanced graphics stack")
            matrix, mode, font = stack.pop()
        elif op == b"cm":
            a, b, c, d, e, f = numbers(args, 6)
            A, B, C, D, E, F = matrix
            matrix = numbers(
                (
                    a * A + b * C,
                    a * B + b * D,
                    c * A + d * C,
                    c * B + d * D,
                    e * A + f * C + E,
                    e * B + f * D + F,
                ),
                6,
            )
        elif op in (b"BT", b"ET"):
            numbers(args, 0)
            if (op == b"BT") == in_text:
                raise Unsupported("Unbalanced text object")
            in_text = op == b"BT"
        elif op == b"Tr":
            (value,) = numbers(args, 1)
            if not in_text or value not in range(8):
                raise Unsupported("Invalid text rendering mode")
            mode = int(value)
            if mode >= 4:
                raise Unsupported("Text clipping not supported")
        elif op == b"Tf":
            if not in_text or len(args) != 2:
                raise Unsupported("Invalid font selection")
            (size,) = numbers(args[1:], 1)
            selected = resource(resources, "/Font", args[0])
            if size <= 0 or selected.get("/Subtype") not in (
                "/Type1",
                "/TrueType",
                "/Type0",
            ):
                raise Unsupported("Unsupported font")
            font = selected
        elif op in (b"Tj", b"TJ", b"'", b'"'):
            if not in_text or font is None:
                raise Unsupported("Text without a valid font")
            if op == b'"':
                if len(args) != 3:
                    raise Unsupported("Invalid quote operator")
                numbers(args[:2], 2)
                values = args[2:]
            elif op == b"TJ":
                if len(args) != 1 or not isinstance(args[0], ArrayObject):
                    raise Unsupported("Invalid text array")
                values = args[0]
            else:
                if len(args) != 1:
                    raise Unsupported("Invalid text show")
                values = args
            nonempty = False
            for value in values:
                if isinstance(value, (TextStringObject, ByteStringObject)):
                    nonempty |= bool(value)
                elif op == b"TJ":
                    numbers([value], 1)
                else:
                    raise Unsupported("Invalid text operand")
            if nonempty:
                if form and mode != 3:
                    raise Unsupported("Form has non-hidden text")
                modes.append(mode)
        elif op in (b"Tm", b"Td", b"TD", b"T*", b"Tc", b"Tw", b"Tz", b"TL", b"Ts"):
            if not in_text:
                raise Unsupported("Text state outside text object")
            numbers(args, {b"Tm": 6, b"Td": 2, b"TD": 2, b"T*": 0}.get(op, 1))
        elif op in (b"g", b"G", b"rg", b"RG", b"k", b"K"):
            color = numbers(args, {b"g": 1, b"G": 1, b"rg": 3, b"RG": 3}.get(op, 4))
            if any(v < 0 or v > 1 for v in color):
                raise Unsupported("Invalid color")
        elif op == b"Do":
            if form:
                raise Unsupported("Nested XObjects in Form unsupported")
            if in_text or len(args) != 1:
                raise Unsupported("Invalid XObject invocation")
            image = resource(resources, "/XObject", args[0])
            if image.get("/Subtype") == "/Form":
                budget["forms"] += 1
                if (
                    budget["forms"] > MAX_FORMS
                    or stack_base + len(stack) + 1 > MAX_STACK
                ):
                    raise Unsupported("Form invocation budget")
                local_resources = form_resources(image)
                local_ops = read_operations([image], pdf, budget)
                _, local_modes = interpret(
                    local_ops,
                    local_resources,
                    pdf,
                    budget,
                    matrix,
                    mode,
                    font,
                    form=True,
                    stack_base=stack_base + len(stack) + 1,
                )
                # Form execution is an implicit save/restore. No local text
                # or graphics state leaks into the following page operations.
                modes.extend(local_modes)
                continue
            if image.get("/Subtype") != "/Image" or any(
                k in image
                for k in ("/SMask", "/SMaskInData", "/Mask", "/ImageMask", "/OC")
            ):
                raise Unsupported("Only ordinary image XObjects supported")
            width, height = numbers([image.get("/Width"), image.get("/Height")], 2)
            if (
                width <= 0
                or height <= 0
                or width != int(width)
                or height != int(height)
            ):
                raise Unsupported("Invalid image dimensions")
            a, b, c, d, e, f = matrix
            if b != 0 or c != 0 or a <= 0 or d <= 0:
                raise Unsupported("Non-axis-aligned image")
            images.append((e, f, e + a, f + d))
        else:
            # Includes gs, sh, inline images, paths, clipping and
            # marked-content/optional-content state. Never silently skip them.
            raise Unsupported("Unsupported operator")
    if stack or in_text:
        raise Unsupported("Unbalanced stream state")
    return images, modes
