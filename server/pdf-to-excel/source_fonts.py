"""Conservative repair of inconsistent simple-font Unicode maps using embedded glyph names.
Only explicit WinAnsi Type1/CFF fonts with standard named glyphs are eligible.
The copied PDF changes extraction metadata, never content streams or font outlines.
"""

from contextlib import contextmanager
from tempfile import TemporaryDirectory
from pypdf.errors import PyPdfError
from pdfminer.pdfexceptions import PDFException
from pathlib import Path
import unicodedata, struct, re
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from pdfminer.latin_enc import ENCODING


def single_byte_map(data, *, allow_wide_declaration=False):
    """Parse bounded ToUnicode bfchar/bfrange records without expanding large ranges."""
    text = re.sub(r"%[^\r\n]*", "", data.decode("ascii"))
    if re.search(r"\b(?:usecmap|begincid\w+|beginnotdef\w+)\b", text):
        return None
    spaces = re.findall(
        r"(\d+)\s+begincodespacerange(.*?)endcodespacerange", text, re.S
    )
    if len(spaces) != 1 or spaces[0][0] != "1":
        return None
    space = re.fullmatch(r"\s*<([0-9a-fA-F]{2})>\s*<([0-9a-fA-F]{2})>\s*", spaces[0][1])
    if space is None:
        # Some simple Type1 fonts declare a two-byte space while all bfchar
        # source codes are one byte. Only the known Type1 caller can opt in;
        # source() below still rejects every actual multibyte entry.
        if not allow_wide_declaration or not re.fullmatch(
            r"\s*<0000>\s*<[fF]{4}>\s*", spaces[0][1]
        ):
            return None
        low, high = 0, 255
    else:
        low, high = [int(x, 16) for x in space.groups()]
    if low > high:
        return None
    pattern = r"(\d+)\s+begin(bfchar|bfrange)\b(.*?)\bend\2\b"
    blocks = list(re.finditer(pattern, text, re.S))
    if not blocks or re.search(
        r"\b(?:begin|end)bf(?:char|range)\b", re.sub(pattern, "", text, flags=re.S)
    ):
        return None
    result = {}

    def source(token):
        if not re.fullmatch(r"<[0-9a-fA-F]{2}>", token):
            raise ValueError("Not a single-byte character")
        code = int(token[1:-1], 16)
        if not low <= code <= high:
            raise ValueError("Character outside code space")
        return code

    def destination(token):
        if not re.fullmatch(r"<(?:[0-9a-fA-F]{4}){1,16}>", token):
            raise ValueError("Invalid UTF-16 destination")
        return bytes.fromhex(token[1:-1])

    for block in blocks:
        count = int(block[1])
        if not 0 <= count <= 256:
            return None
        tokens = re.findall(r"<[^>]*>|\[|\]|[^\s]+", block[3])
        cursor = 0
        for _ in range(count):
            first = source(tokens[cursor])
            cursor += 1
            if block[2] == "bfchar":
                last = first
                raw = [destination(tokens[cursor])]
                cursor += 1
            else:
                last = source(tokens[cursor])
                cursor += 1
                if last < first:
                    return None
                length = last - first + 1
                if tokens[cursor] == "[":
                    cursor += 1
                    raw = [destination(t) for t in tokens[cursor : cursor + length]]
                    cursor += length
                    if len(raw) != length or tokens[cursor] != "]":
                        return None
                    cursor += 1
                else:
                    initial = destination(tokens[cursor])
                    cursor += 1
                    value = int.from_bytes(initial, "big")
                    raw = [
                        (value + i).to_bytes(len(initial), "big") for i in range(length)
                    ]
            for code, value in zip(range(first, last + 1), raw, strict=True):
                if code in result:
                    return None
                result[code] = value.decode("utf-16-be")
        if cursor != len(tokens):
            return None
    return result or None


def font_repairs(font):
    if font.get("/Subtype") != "/Type1" or "/ToUnicode" not in font:
        return None
    enc = font.get("/Encoding")
    if hasattr(enc, "get_object"):
        enc = enc.get_object()
    if enc == "/WinAnsiEncoding":
        differences = []
    elif isinstance(enc, dict) and enc.get("/BaseEncoding") == "/WinAnsiEncoding":
        differences = enc.get("/Differences", [])
    else:
        return None
    descriptor = font.get("/FontDescriptor")
    if not descriptor:
        return None
    stream = descriptor.get_object().get("/FontFile3")
    if not stream or stream.get_object().get("/Subtype") != "/Type1C":
        return None
    raw = stream.get_object().get_data()
    cmap = font["/ToUnicode"].get_data()
    if not 0 < len(raw) <= 2_000_000 or not 0 < len(cmap) <= 65536:
        return None
    from cff_names import glyph_names

    names = glyph_names(raw)
    if names is None:
        return None
    encoding = {win: name for name, std, mac, win, pdf in ENCODING if win is not None}
    code = None
    for entry in differences:
        if isinstance(entry, int):
            code = entry
        elif (
            isinstance(entry, str)
            and entry.startswith("/")
            and code is not None
            and 0 <= code <= 255
        ):
            encoding[code] = entry[1:]
            code += 1
        else:
            return None
    original = single_byte_map(cmap, allow_wide_declaration=True)
    if not original or any(not 0 <= k <= 255 for k in original):
        return None
    changes = {}
    for code, current in original.items():
        name = encoding.get(code)
        if name not in names:
            continue
        # Restrict to exact ASCII letter names or explicit f-ligature names.
        if len(name) == 1 and name.isascii() and name.isalpha():
            expected = name
            eligible = (
                len(current) == 1
                and current.isascii()
                and current.isalpha()
                and current.casefold() == expected.casefold()
            )
        elif name in {"f_i", "f_f", "f_l", "f_f_i", "f_f_l"}:
            expected = name.replace("_", "")
            eligible = (
                current in {"f", "i", "l", "fi", "fl", "ff"}
                and current != expected
                and unicodedata.normalize("NFKC", current) != expected
            )
        else:
            continue
        if eligible and current != expected:
            changes[code] = dict(before=current, after=expected, glyph=name)
    if not changes:
        return None
    updated = dict(original)
    updated.update({code: value["after"] for code, value in changes.items()})
    lines = [
        b"/CIDInit /ProcSet findresource begin",
        b"12 dict begin begincmap",
        b"/CMapType 2 def",
        b"/CMapName /VerifiedEmbeddedGlyphs def",
        b"1 begincodespacerange",
        b"<00> <FF>",
        b"endcodespacerange",
    ]
    entries = sorted(updated.items())
    for start in range(0, len(entries), 100):
        chunk = entries[start : start + 100]
        lines.append(f"{len(chunk)} beginbfchar".encode())
        lines.extend(
            f'<{code:02X}> <{value.encode("utf-16-be").hex().upper()}>'.encode()
            for code, value in chunk
        )
        lines.append(b"endbfchar")
    lines.extend([b"endcmap CMapName currentdict /CMap defineresource pop", b"end end"])
    return b"\n".join(lines), changes


def repair(source, output, reader=None):
    reader = reader if reader is not None else PdfReader(source)
    if reader.is_encrypted:
        return []
    visited = set()
    fonts = []

    def walk(resources, depth=0):
        if not resources or depth > 10 or len(visited) > 2048:
            return
        resources = resources.get_object()
        if id(resources) in visited:
            return
        visited.add(id(resources))
        for ref in (
            resources.get("/Font", {}).get_object().values()
            if "/Font" in resources
            else []
        ):
            font = ref.get_object()
            if id(font) not in visited:
                visited.add(id(font))
                fonts.append(font)
        for ref in (
            resources.get("/XObject", {}).get_object().values()
            if "/XObject" in resources
            else []
        ):
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Form":
                walk(obj.get("/Resources"), depth + 1)

    for page in reader.pages:
        walk(page.get("/Resources"))
    if len(fonts) > 256:
        return []
    repairs = []
    for font in fonts:
        try:
            result = font_repairs(font)
        except (
            ValueError,
            KeyError,
            TypeError,
            AssertionError,
            IndexError,
            EOFError,
            UnicodeError,
            OverflowError,
            struct.error,
        ):
            continue
        if result:
            content, changes = result
            stream = DecodedStreamObject()
            stream.set_data(content)
            font[NameObject("/ToUnicode")] = stream
            repairs.append(dict(font=str(font.get("/BaseFont")), changes=changes))
    if repairs:
        writer = PdfWriter(clone_from=reader)
        writer.write(output)
    return repairs


@contextmanager
def prepared_source(source, reader, output_directory):
    """Keep repairs local to one conversion, preserving the uploaded original."""
    with TemporaryDirectory(prefix=".pdf-excel-fonts-", dir=output_directory) as folder:
        output = Path(folder) / "input.pdf"
        try:
            changes = repair(source, output, reader)
        except (
            PyPdfError,
            PDFException,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            AssertionError,
            IndexError,
            EOFError,
            UnicodeError,
            OverflowError,
            struct.error,
        ):
            changes = []
        yield output if changes else source
