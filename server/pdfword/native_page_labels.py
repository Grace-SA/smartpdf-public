"""Conservative source evidence for a single-page numeric footer."""
import re


def numeric_footer(page):
    words = page.extract_words()
    margin = [w for w in words if w['top'] > page.height * .92]
    if len(margin) != 1 or len(words) < 2:
        return None
    word = margin[0]
    if (not re.fullmatch(r'[0-9]{1,4}', word['text'])
            or not 0 <= word['x0'] < word['x1'] <= page.width
            or not word['top'] < word['bottom'] <= page.height
            or word['bottom'] - word['top'] > 20
            or any(w is not word and w['bottom'] > word['top'] - 8 for w in words)):
        return None
    return word['text']
