"""Bounded contrast recovery for dark monochrome scans before orientation."""

def prepare_dark_document(image):
    import cv2
    import numpy as np
    from scan_orientation import line_axis
    unchanged = {'dark_contrast_stretched': False}
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        return (image, unchanged)
    if np.any(image.max(axis=2) != image.min(axis=2)):
        return (image, unchanged)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lo, hi = (int(gray.min()), int(gray.max()))
    if lo != 0 or not 8 <= hi <= 32:
        return (image, unchanged)
    mode = int(np.bincount(gray.ravel(), minlength=256).argmax())
    if mode < 8:
        return (image, unchanged)
    paper = float(np.mean(np.abs(gray.astype(np.int16) - mode) <= 1))
    if paper < 0.55:
        return (image, unchanged)
    evidence = line_axis(image)
    if not evidence or not (evidence['horizontal_ratio'] >= 1.5 or evidence['horizontal_ratio'] <= 2 / 3):
        return (image, unchanged)
    corrected = np.rint(image.astype(np.float32) * 245 / hi).clip(0, 255).astype(np.uint8)
    return (corrected, dict(dark_contrast_stretched=True, original_range=[lo, hi], paper_fraction=paper))
