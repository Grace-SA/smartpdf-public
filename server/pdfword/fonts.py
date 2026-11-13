"""Bounded common PDF font-family aliases; never embed or fetch fonts."""
import re

# Preserve familiar family intent without trusting arbitrary PDF names as OOXML
# font identifiers. Unknown/embedded custom families retain the existing fallback.
FAMILIES = {
    'arial': 'Arial', 'arialmt': 'Arial', 'arialboldmt': 'Arial',
    'arialitalicmt': 'Arial', 'arialbolditalicmt': 'Arial',
    'helvetica': 'Arial', 'helveticabold': 'Arial', 'helveticaoblique': 'Arial',
    'helveticaboldoblique': 'Arial',
    'timesroman': 'Times New Roman', 'timesbold': 'Times New Roman',
    'timesitalic': 'Times New Roman', 'timesbolditalic': 'Times New Roman',
    'timesnewromanpsmt': 'Times New Roman', 'timesnewromanpsboldmt': 'Times New Roman',
    'timesnewromanpsitalicmt': 'Times New Roman', 'timesnewromanpsbolditalicmt': 'Times New Roman',
    'courier': 'Courier New', 'courierbold': 'Courier New',
    'courieroblique': 'Courier New', 'courierboldoblique': 'Courier New',
    'couriernewpsmt': 'Courier New', 'couriernewpsboldmt': 'Courier New',
    'couriernewpsitalicmt': 'Courier New', 'couriernewpsbolditalicmt': 'Courier New',
}
for family in ('Times New Roman', 'Courier New', 'Calibri', 'Cambria', 'Carlito', 'Liberation Serif', 'Liberation Sans', 'Liberation Mono'):
    for style in ('', 'Regular', 'Bold', 'Italic', 'BoldItalic'):
        FAMILIES[re.sub('[^a-z]', '', (family + style).lower())] = family

SAFE_FAMILIES = frozenset(FAMILIES.values())


def font_family(name):
    name = re.sub(r'^[A-Za-z]{6}\+', '', name)
    return FAMILIES.get(re.sub('[^a-z]', '', name.lower()), 'Arial')
