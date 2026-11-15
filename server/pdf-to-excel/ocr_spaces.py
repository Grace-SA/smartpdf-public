"""Recover missing OCR word spaces only with pixel and recognition consensus.

Letters and numbers are never changed. A one-to-one character projection, a
large blank gap, and two high-confidence padded recognitions must all agree.
Only short ASCII alphabetic runs are eligible; uncertain results stay intact.
"""

import math
import re
from statistics import median
from numbers import Real
import cv2, numpy as np


def recover_spaces(image, result, reader):
    from ocr_touching_spaces import recover_touching_spaces

    projected = _recover_projected_spaces(image, result, reader)
    return recover_touching_spaces(image, projected, reader)


def _recover_projected_spaces(image, result, reader):
    if not result:
        return result
    candidates = []
    crops = []
    for idx, (box, text, score) in enumerate(result):
        if not re.fullmatch(r"[A-Za-z]{3,32}", text) or score < 0.85:
            continue
        points = np.asarray(box)
        x0, y0 = np.floor(points.min(axis=0)).astype(int)
        x1, y1 = np.ceil(points.max(axis=0)).astype(int)
        if (
            y1 - y0 < 8
            or abs(box[0][1] - box[1][1]) > 2
            or abs(box[2][1] - box[3][1]) > 2
        ):
            continue
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(image.shape[1], x1)
        y1 = min(image.shape[0], y1)
        crop = image[y0:y1, x0:x1]
        if not crop.size:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        yy, xx = np.where(bw > 0)
        if not len(yy):
            continue
        height = int(np.ptp(yy)) + 1
        mask = (bw > 0).sum(axis=0) > max(1, height * 0.05)
        starts = np.where(np.diff(np.pad(mask.astype(int), (1, 1))) == 1)[0]
        ends = np.where(np.diff(np.pad(mask.astype(int), (1, 1))) == -1)[0]
        if len(starts) != len(text):
            continue
        gaps = starts[1:] - ends[:-1]
        splits = [
            i + 1
            for i, gap in enumerate(gaps)
            if gap >= max(3, height * 0.22, median(gaps) * 2.5)
        ]
        if not splits:
            continue
        expected = "".join(
            (" " if i in splits else "") + ch for i, ch in enumerate(text)
        )
        alternatives = []
        for factor in [0.15, 0.25]:
            pad = max(2, round((y1 - y0) * factor))
            alternatives.append(
                image[
                    max(0, y0 - pad) : min(image.shape[0], y1 + pad),
                    max(0, x0 - pad) : min(image.shape[1], x1 + pad),
                ]
            )
        candidates.append((idx, expected))
        crops.extend(alternatives)
        if len(candidates) >= 48:
            break
    if not candidates:
        return result
    recognized, _ = reader.text_rec(crops)
    if recognized is None or len(recognized) != len(crops):
        return result
    if any(not isinstance(row, (list, tuple)) or len(row) < 2 for row in recognized):
        return result
    out = [list(row) for row in result]
    for j, (idx, expected) in enumerate(candidates):
        matches = recognized[j * 2 : j * 2 + 2]
        if len(matches) == 2 and all(
            isinstance(t, str)
            and t.strip(" \t\r\n") == expected
            and isinstance(s, Real)
            and math.isfinite(s)
            and 0.95 <= s <= 1
            for t, s, *_ in matches
        ):
            out[idx][1] = expected
            out[idx][2] = min(out[idx][2], *(float(s) for _, s, *_ in matches))
    return out
