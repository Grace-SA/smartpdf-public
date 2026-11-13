"""Recover touching-letter word spacing only with pixel and six-way OCR evidence.

No letters, digits or punctuation are changed. At most eight eligible candidates
receive recognition per OCR result batch, with at most ten small crops per candidate.
"""

import math
import re
from numbers import Real
from statistics import median

import cv2
import numpy as np


def recover_touching_spaces(image, result, reader):
    if not result:
        return result
    out = [list(row) for row in result]
    attempts = 0
    for index, (box, text, score) in enumerate(result):
        if attempts >= 8:
            break
        info = recover_candidate(image, box, text, score, reader)
        if "crop_count" in info:
            attempts += 1
        if info["accepted"]:
            out[index][1] = info["replacement"]
            out[index][2] = min(float(score), info["confidence"])
    return out


def recover_candidate(im, box, text, score, reader):
    info = {"original": text, "accepted": False}
    if (
        not re.fullmatch("[A-Za-z]{6,32}", text)
        or not isinstance(score, Real)
        or not math.isfinite(score)
        or not 0.95 <= score <= 1
    ):
        return info | {"reason": "input"}
    ps = np.asarray(box)
    x0, y0 = np.floor(ps.min(axis=0)).astype(int)
    x1, y1 = np.ceil(ps.max(axis=0)).astype(int)
    if (
        x0 < 0
        or y0 < 0
        or x1 > im.shape[1]
        or y1 > im.shape[0]
        or x1 <= x0
        or y1 - y0 < 8
        or abs(box[0][1] - box[1][1]) > 2
        or abs(box[2][1] - box[3][1]) > 2
    ):
        return info | {"reason": "geometry"}
    crop = im[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    yy, _xx = np.where(bw > 0)
    if not len(yy):
        return info | {"reason": "blank"}
    height = int(np.ptp(yy)) + 1
    mask = (bw > 0).sum(axis=0) > max(1, height * 0.05)
    starts = np.where(np.diff(np.pad(mask.astype(int), (1, 1))) == 1)[0]
    ends = np.where(np.diff(np.pad(mask.astype(int), (1, 1))) == -1)[0]
    if not 2 <= len(starts) < len(text):
        return info | {"reason": "component-count", "components": len(starts)}
    gaps = starts[1:] - ends[:-1]
    cuts = [
        round((ends[i] + starts[i + 1]) / 2)
        for i, g in enumerate(gaps)
        if g >= max(3, height * 0.22, median(gaps) * 2.5)
    ]
    if not 1 <= len(cuts) <= 3:
        return info | {"reason": "gap-count", "cuts": cuts}
    crops = []
    for f in [0.15, 0.25]:
        p = max(2, round((y1 - y0) * f))
        crops.append(
            im[
                max(0, y0 - p) : min(im.shape[0], y1 + p),
                max(0, x0 - p) : min(im.shape[1], x1 + p),
            ]
        )
    for a, b in zip([0] + cuts, cuts + [crop.shape[1]]):
        for f in [0.15, 0.25]:
            p = max(2, round((y1 - y0) * f))
            crops.append(
                cv2.copyMakeBorder(
                    crop[:, a:b], p, p, p, p, cv2.BORDER_CONSTANT, value=(255, 255, 255)
                )
            )
    pred, _ = reader.text_rec(crops)
    info |= {"components": len(starts), "cuts": cuts, "crop_count": len(crops)}
    if pred is None or len(pred) != len(crops):
        return info | {"reason": "batch"}
    if any(
        not isinstance(r, (tuple, list))
        or len(r) < 2
        or not isinstance(r[0], str)
        or not isinstance(r[1], Real)
        or not math.isfinite(r[1])
        or not 0.95 <= r[1] <= 1
        for r in pred
    ):
        return info | {"reason": "confidence"}
    texts = [r[0].strip(" \t\r\n") for r in pred]
    expected = texts[0]
    if (
        texts[1] != expected
        or not re.fullmatch("[A-Za-z]+(?: [A-Za-z]+){1,3}", expected)
        or expected.replace(" ", "") != text
    ):
        return info | {"reason": "line-consensus"}
    words = expected.split(" ")
    if len(words) != len(cuts) + 1:
        return info | {"reason": "word-count"}
    if any(texts[2 + 2 * i : 4 + 2 * i] != [w, w] for i, w in enumerate(words)):
        return info | {"reason": "word-consensus"}
    return info | {
        "reason": "accepted",
        "accepted": True,
        "replacement": expected,
        "confidence": min(float(r[1]) for r in pred),
    }
