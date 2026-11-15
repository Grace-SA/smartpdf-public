"""Normalize Java OPC output without weakening the independent DOCX checker."""
import hashlib
import io
import posixpath
import re
import zipfile
from pathlib import Path

from lxml import etree as E
from PIL import Image

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
N = {"w": W, "r": R}


def w(name):
    return "{" + W + "}" + name


def prop(parent, name, **attributes):
    element = parent.find(w(name))
    if element is None:
        element = E.SubElement(parent, w(name))
    for key, value in attributes.items():
        element.set(w(key), str(value))
    return element


def text(element):
    return " ".join(element.xpath(".//w:t/text()", namespaces=N))


def normalize_package(source, destination, page_count):
    parts, media = {}, {}
    decoded_pixels = encoded_media = 0
    parser = E.XMLParser(resolve_entities=False, no_network=True)
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if (len(infos) > 4096 or sum(i.file_size for i in infos) > 96 * 1024**2
                or len({i.filename for i in infos}) != len(infos)):
            raise ValueError("Native package exceeds normalization budget")
        for info in infos:
            name = info.filename
            if info.is_dir():
                continue
            if (not re.fullmatch(r"[\w\[\]./-]+", name) or name.startswith("/")
                    or ".." in name.split("/") or info.file_size > 16 * 1024**2
                    or info.flag_bits & ~0x808):
                raise ValueError("Unexpected native package part")
            value = archive.read(info)  # Verifies CRC, including Java data descriptors.
            if name.startswith("word/media/"):
                with Image.open(io.BytesIO(value)) as image:
                    if image.width * image.height > 16000000 or image.format not in ("PNG", "JPEG"):
                        raise ValueError("Native image exceeds budget")
                    decoded_pixels += image.width * image.height
                    if decoded_pixels > 64000000:
                        raise ValueError("Native decoded image budget exceeded")
                    out = io.BytesIO()
                    image.convert("RGBA" if "A" in image.getbands() else "RGB").save(out, format="PNG")
                    media[name] = out.getvalue()
                    encoded_media += len(media[name])
                    if encoded_media > 32 * 1024**2:
                        raise ValueError("Native image package budget exceeded")
            elif name.endswith((".xml", ".rels")):
                if re.search(br"<!DOCTYPE|<!ENTITY", value, re.I):
                    raise ValueError("Native XML declarations refused")
                parts[name] = E.fromstring(value, parser)
            else:
                raise ValueError("Unexpected binary part")

    root = parts["word/document.xml"]
    body = root.find(w("body"))
    if body is None:
        raise ValueError("Missing native document body")
    # Keep the proven structured exporter for columns until native column flow is verified.
    if any(int(c.get(w("num"), "1")) > 1 for c in root.iter(w("cols"))):
        raise ValueError("Use structured column reconstruction")

    marks = [m for m in root.iter(w("bookmarkStart")) if re.fullmatch(r"_Pg\d+", m.get(w("name"), ""))]
    if [m.get(w("name")) for m in marks] != [f"_Pg{i+1}" for i in range(page_count)]:
        raise ValueError("Missing or reordered source page bookmarks")
    for i, mark in enumerate(marks):
        mark.set(w("name"), f"smartpdf_page_{i+1}")

    # Identical grids across a short document are handled by the existing continuation model.
    tables = list(body.iter(w("tbl")))
    if 1 < page_count <= 5 and len(tables) == page_count:
        grids = [[int(c.get(w("w"))) for c in t.findall("w:tblGrid/w:gridCol", N)] for t in tables]
        if grids[0] and all(len(g) == len(grids[0]) and all(abs(a-b) < 40 for a, b in zip(g, grids[0])) for g in grids):
            raise ValueError("Use structured cross-page table reconstruction")

    # Restore usable page width: engine inferred right margins can consume most of a page.
    sections = list(root.iter(w("sectPr")))
    for section in sections:
        margins = section.find(w("pgMar"))
        if margins is not None:
            margins.set(w("right"), str(min(720, int(margins.get(w("right"), "720")))))
    # Find the section that owns each body element (OOXML section properties occur at its end).
    available = {}
    last = sections[-1] if sections else None
    for element in reversed(list(body)):
        section = element if element.tag == w("sectPr") else element.find(".//w:sectPr", N)
        if section is not None:
            last = section
        if last is None:
            raise ValueError("Missing page geometry")
        size, margins = last.find(w("pgSz")), last.find(w("pgMar"))
        if size is None or margins is None:
            raise ValueError("Missing native margins")
        width = int(size.get(w("w"))) - int(margins.get(w("left"), "0")) - int(margins.get(w("right"), "0"))
        available[element] = width
    for table in tables:
        if any(parent.tag == w("tbl") for parent in table.iterancestors()):
            raise ValueError("Use structured nested-table reconstruction")
        owner = table
        while owner.getparent() is not body:
            owner = owner.getparent()
        width = available[owner]
        grid = table.findall("w:tblGrid/w:gridCol", N)
        old = [int(c.get(w("w"))) for c in grid]
        if not old or min(old) <= 0 or width <= 0:
            raise ValueError("Invalid native table geometry")
        total = min(sum(old), width)
        sizes = [max(1, round(v * total / sum(old))) for v in old]
        sizes[-1] += total - sum(sizes)
        if min(sizes) <= 0:
            raise ValueError("Native grid cannot fit the page")
        for col, value in zip(grid, sizes):
            col.set(w("w"), str(value))
        properties = table.find(w("tblPr"))
        if properties is None:
            properties = E.Element(w("tblPr")); table.insert(0, properties)
        prop(properties, "tblW", type="dxa", w=total)
        prop(properties, "tblInd", type="dxa", w=0)
        prop(properties, "tblLayout", type="fixed")
        padding = max(0, min(40, (min(sizes) - 40) // 2))
        margins = prop(properties, "tblCellMar")
        for side in ("left", "right"):
            prop(margins, side, type="dxa", w=padding)
        for row in table.findall(w("tr")):
            index = 0
            for cell in row.findall(w("tc")):
                cp = cell.find(w("tcPr"))
                if cp is None:
                    cp = E.Element(w("tcPr")); cell.insert(0, cp)
                span = cp.find(w("gridSpan"))
                count = int(span.get(w("val"))) if span is not None else 1
                if index + count > len(sizes):
                    raise ValueError("Native row exceeds grid")
                prop(cp, "tcW", type="dxa", w=sum(sizes[index:index+count]))
                index += count

    # Normalize images and relations; deduplicate exact pixels without changing content.
    output_media, renamed, hashes = {}, {}, {}
    for name, value in media.items():
        sha = hashlib.sha256(value).hexdigest()
        target = hashes.setdefault(sha, f"word/media/image{len(hashes)+1}.png")
        renamed[name] = target
        output_media[target] = value
    for name, tree in parts.items():
        if not name.endswith(".rels"):
            continue
        base = "" if name == "_rels/.rels" else re.sub(r"_rels/([^/]+)\.rels$", r"\1", name)
        for relation in tree:
            if relation.get("TargetMode"):
                raise ValueError("External native relation refused")
            target = relation.get("Target", "")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base), target))
            if resolved in renamed:
                relation.set("Target", posixpath.relpath(renamed[resolved], posixpath.dirname(base)))
    types = parts["[Content_Types].xml"]
    for entry in list(types):
        if entry.get("Extension", "").lower() in ("jpg", "jpeg", "png"):
            types.remove(entry)
    E.SubElement(types, "{" + E.QName(types).namespace + "}Default", Extension="png", ContentType="image/png")

    # Retain visible field results, never carry executable field instructions into this service.
    for tree in parts.values():
        for element in list(tree.iter()):
            if element.tag in (w("instrText"), w("fldChar")):
                element.getparent().remove(element)

    page_text = [[] for _ in range(page_count)]
    page_images = [0 for _ in range(page_count)]
    # The engine anchors its first-page bookmark to the first paragraph, which may
    # follow a leading table. Content before that anchor still belongs to page 1.
    current = 0
    for element in body.iter():
        if element.tag == w("bookmarkStart"):
            match = re.fullmatch(r"smartpdf_page_(\d+)", element.get(w("name"), ""))
            if match:
                current = int(match[1]) - 1
        elif element.tag == w("t") and current >= 0:
            page_text[current].append(element.text or "")
        elif E.QName(element).localname == "blip" and current >= 0:
            page_images[current] += 1
    # Shared headers/footers can be defined once while applying to every source page.
    margin_text = " ".join(text(t) for name, t in parts.items() if re.fullmatch(r"word/(header|footer)\d*\.xml", name))
    page_text = [" ".join(values) + " " + margin_text for values in page_text]
    output = {name: E.tostring(tree, encoding="UTF-8", xml_declaration=True) for name, tree in parts.items()}
    output.update(output_media)
    if (len(output) > 1024 or sum(map(len, output.values())) > 32 * 1024**2
            or any(len(value) > 8 * 1024**2 for value in output.values())):
        raise ValueError("Normalized native output exceeds product budget")
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, value in output.items():
            archive.writestr(name, value)
    if Path(destination).stat().st_size > 30 * 1024**2:
        raise ValueError("Native output exceeds download budget")
    images = sum(sum(E.QName(e).localname == "blip" for e in tree.iter()) for tree in parts.values())
    return dict(schema=2, pages=page_count, images=images, tables=len(tables), nativePageImages=page_images, warnings=[]), page_text
