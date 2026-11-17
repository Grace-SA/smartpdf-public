"""Conservative fast path for dense, closed, unmerged source grids."""

from collections import Counter
from layout_tables import visible_box
from text_tables import aligned_tables


def dense_grid(page, native):
    if len(native) != 1 or page.rotation:
        return None
    t = native[0]
    rows, cols = len(t["heights"]), len(t["widths"])
    cells = t["cells"]
    if not t.get("closedGrid") or rows < 20 or cols < 5 or rows * cols < 150:
        return None
    if len(cells) != rows * cols or any(c["rs"] != 1 or c["cs"] != 1 for c in cells):
        return None
    if sum(bool(c["text"].strip()) for c in cells) < rows * cols * 0.95:
        return None
    if sum("\n" in c["text"] for c in cells) > len(
        cells
    ) * 0.05 and not enumerated_rows(t):
        return None
    columns = [[c["text"] for c in cells if c["c"] == col] for col in range(cols)]
    numeric = sum(
        sum(any(ch.isdigit() for ch in value) for value in column) >= rows * 0.8
        for column in columns
    )
    labels = sum(
        sum(any(ch.isalpha() for ch in value) for value in column) >= rows * 0.8
        for column in columns
    )
    if numeric < 2 or labels < 2:
        return None
    b = t["bbox"]
    view = visible_box(page)
    if (b[2] - b[0]) * (b[3] - b[1]) < (view[2] - view[0]) * (view[3] - view[1]) * 0.5:
        return None
    visible = [
        c
        for c in page.chars
        if view[0] <= (c["x0"] + c["x1"]) / 2 <= view[2]
        and view[1] <= (c["top"] + c["bottom"]) / 2 <= view[3]
    ]
    chars = [
        c
        for c in visible
        if b[0] <= (c["x0"] + c["x1"]) / 2 <= b[2]
        and b[1] <= (c["top"] + c["bottom"]) / 2 <= b[3]
    ]
    if (
        not chars
        or len(chars) < len(visible) * 0.9
        or any(not c["upright"] for c in chars)
    ):
        return None
    # A dense grid cannot suppress a separate borderless table or a substantial
    # image region. Such pages retain the full layout-model path.
    if aligned_tables(page.crop(tuple(view)), excluded=[b]):
        return None
    area = (view[2] - view[0]) * (view[3] - view[1])
    if any(
        (image["x1"] - image["x0"]) * (image["bottom"] - image["top"]) > area * 0.05
        for image in page.images
    ):
        return None
    before = Counter(ch for c in chars for ch in c["text"] if not ch.isspace())
    after = Counter(ch for c in cells for ch in c["text"] if not ch.isspace())
    if before != after or any("(cid:" in c["text"] for c in cells):
        return None
    return dict(
        t,
        method="dense-grid",
        sourceGeometry=True,
        headerRows=int(
            all(
                any(ch.isalpha() for ch in c["text"])
                and not any(ch.isdigit() for ch in c["text"])
                for c in cells
                if c["r"] == 0
            )
        ),
    )


def enumerated_rows(table):
    """Allow wrapped records only when every physical row has its own serial."""
    rows = len(table["heights"])
    serial = {c["r"]: c["text"].strip() for c in table["cells"] if c["c"] == 0}
    return (
        len(serial) == rows
        and any(ch.isalpha() for ch in serial.get(0, ""))
        and all(serial.get(r) == str(r) for r in range(1, rows))
    )
