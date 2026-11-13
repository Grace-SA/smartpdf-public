import cv2, numpy as np
from statistics import median


def from_pixels(text, image):
    flat = "".join(text.split())
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1] > 0
    cols = np.any(ink, axis=0)
    runs = []
    for x, v in enumerate(cols):
        if v and (x == 0 or not cols[x - 1]):
            start = x
        if v and (x == len(cols) - 1 or not cols[x + 1]):
            runs.append((start, x))
    if len(runs) != len(flat) or len(runs) < 4:
        return None, dict(count=len(runs), expected=len(flat))
    centers = [(a + b) / 2 for a, b in runs]
    gaps = np.diff(centers)
    pitch = float(median(gaps))
    steps = [max(1, round(g / pitch)) for g in gaps]
    if (
        pitch < 3
        or sum(s == 1 for s in steps) < len(steps) * 0.6
        or any(abs(g - s * pitch) > pitch * 0.22 for g, s in zip(gaps, steps))
    ):
        return None, dict(pitch=pitch, gaps=gaps.tolist())
    result = flat[0] + "".join(" " * (s - 1) + ch for s, ch in zip(steps, flat[1:]))
    return result, dict(pitch=pitch, steps=steps)
