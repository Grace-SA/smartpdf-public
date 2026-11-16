"""Conservative CJK font comparison without inter-character spacing bias.

Only separated, horizontal CJK-only strings are supported. This estimates a
substitute font; it does not establish original font identity or OCR truth.
"""
import numpy as np
from PIL import Image, ImageDraw


def _normalized(ink):
    points = np.argwhere(ink > .2)
    if not len(points):
        return None
    top, left = points.min(axis=0)
    bottom, right = points.max(axis=0) + 1
    mask = Image.fromarray(np.uint8(np.clip(ink[top:bottom, left:right] * 255, 0, 255)))
    return np.asarray(mask.resize((16, 16), Image.Resampling.LANCZOS), dtype=float) / 255


class GlyphEvidence:
    def __init__(self, text, ink):
        self.text = text
        self.ink = ink
        self.samples = {}
        self.cuts = []
        if not 4 <= len(text) <= 64 or not all('\u3400' <= c <= '\u9fff' for c in text):
            return
        height, width = ink.shape
        if not 8 <= height <= 256 or not 1 <= width <= 4096:
            return
        empty = np.flatnonzero(~(ink > .2).any(axis=0))
        groups = np.split(empty, np.flatnonzero(np.diff(empty) > 1) + 1)
        cuts = [0, width] + [int(round((g[0] + g[-1]) / 2)) for g in groups
                             if len(g) and 0 < g[0] and g[-1] < width - 1]
        if len(text) + 1 <= len(set(cuts)) <= 4 * len(text):
            self.cuts = sorted(set(cuts))

    def score(self, font):
        if not self.cuts:
            return None
        height, width = self.ink.shape
        advance = width / len(self.text)
        states = {0: (0., 0.)}
        for index, char in enumerate(self.text):
            left, top, right, bottom = font.getbbox(char)
            if not 0 < right - left <= 256 or not 0 < bottom - top <= 256:
                return None
            mask = Image.new('L', (right - left, bottom - top))
            ImageDraw.Draw(mask).text((-left, -top), char, font=font, fill=255)
            template = _normalized(np.asarray(mask, dtype=float) / 255)
            if template is None:
                return None
            expected = (index + 1) * advance
            ends = [width] if index == len(self.text) - 1 else sorted(
                (x for x in self.cuts if 0 < x < width and abs(x - expected) <= 2 * height),
                key=lambda x: (abs(x - expected), x))[:12]
            next_states = {}
            for end in ends:
                for start, (cost, worst) in states.items():
                    if not .35 * advance <= end - start <= 1.8 * advance:
                        continue
                    key = start, end
                    if key not in self.samples:
                        self.samples[key] = _normalized(self.ink[:, start:end])
                    sample = self.samples[key]
                    if sample is None:
                        continue
                    error = float(np.abs(sample - template).sum() / max(1, sample.sum() + template.sum()))
                    candidate = cost + error, max(worst, error)
                    if end not in next_states or candidate < next_states[end]:
                        next_states[end] = candidate
            states = next_states
            if not states:
                return None
        total, worst = states[width]
        return total / len(self.text), worst


def rerank(text, ink, choices, fonts):
    """Keep whole-line error for the existing admission gate; only rerank."""
    baseline = choices[0]
    if baseline['error'] <= .12:
        return baseline
    evidence = GlyphEvidence(text, ink)
    ranked = []
    for choice in choices:
        score = evidence.score(fonts[choice['path'], choice['weight']])
        if score is not None:
            ranked.append((score, choice))
    ranked.sort(key=lambda item: item[0])
    if len(ranked) < 2 or not any(choice is baseline for _, choice in ranked):
        return baseline
    (error, worst), winner = ranked[0]
    if winner is baseline or error > .18 or worst > .30 or ranked[1][0][0] - error < .03 or winner['error'] > .30:
        return baseline
    # Do not replace an already usable fallback with a face whose required
    # tracking exceeds the geometry fitter's conservative range. Leave margin
    # below its 0.2em cap for rasterization and Office metric differences.
    font = fonts[winner['path'], winner['weight']]
    left, top, right, bottom = font.getbbox(text)
    mask = Image.new('L', (right - left, bottom - top))
    ImageDraw.Draw(mask).text((-left, -top), text, font=font, fill=255)
    bounds = mask.getbbox()
    if not bounds:
        return baseline
    scale = ink.shape[0] / (bounds[3] - bounds[1])
    tracking = (ink.shape[1] - (bounds[2] - bounds[0]) * scale) / (len(text) - 1)
    if abs(tracking) > .15 * font.size * scale:
        return baseline
    return dict(winner, glyph_error=error,
                comparison='open CJK family and weight ink; separated glyphs rank only')
