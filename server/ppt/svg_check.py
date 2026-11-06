"""Bounded static SVG images. No scripts, animation, external or embedded files."""
import math
import re
from xml.etree import ElementTree as ET

SVG = '{http://www.w3.org/2000/svg}'
XLINK = '{http://www.w3.org/1999/xlink}'
XML = '{http://www.w3.org/XML/1998/namespace}'
TAGS = set('svg g defs symbol use path rect circle ellipse line polyline polygon text tspan textPath title desc style linearGradient radialGradient stop clipPath mask marker'.split())
ELEMENTS = {SVG + name for name in TAGS}
PROPERTIES = set('fill fill-rule fill-opacity stroke stroke-width stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset stroke-opacity opacity color stop-color stop-opacity font-family font-size font-style font-weight font-stretch font-variant text-anchor dominant-baseline alignment-baseline baseline-shift letter-spacing word-spacing text-decoration visibility display overflow clip-path mask marker-start marker-mid marker-end paint-order vector-effect'.split())
ATTRS = PROPERTIES | set('id class style version baseProfile width height viewBox preserveAspectRatio x y x1 y1 x2 y2 cx cy r rx ry dx dy d points transform gradientTransform gradientUnits spreadMethod offset fx fy fr clipPathUnits maskUnits maskContentUnits markerUnits markerWidth markerHeight refX refY orient textLength lengthAdjust rotate href'.split())
IDENTIFIER = r'[A-Za-z0-9_.:-]{1,128}'
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


class SVGRejected(ValueError):
    pass


def reject(message='This SVG contains unsupported or active content. Use a static SVG or PNG image.'):
    raise SVGRejected(message)


def inspect_svg(raw, budget):
    if not 0 < len(raw) <= 4 * 1024**2:
        reject('An SVG image exceeds the 4 MiB resource limit.')
    try:
        text = raw.decode('utf-8-sig', errors='strict')
        if ('\x00' in text or re.search(r'<!\s*(?:DOCTYPE|ENTITY)|<\?(?!xml\s)', text, re.I)):
            reject()
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError):
        reject('An SVG image is damaged or uses an unsupported encoding.')
    if root.tag != SVG + 'svg':
        reject('An SVG image must use the standard SVG namespace.')
    identifiers, references, nodes = {}, {}, []

    def value_refs(value):
        # CSS escapes/imports and control characters cannot hide a fetch target.
        if any(c in value for c in ('\\', '@', '\x00')) or re.search(r'(?i)\b(?:expression|var|env)\s*\(|(?:https?|file|data|javascript):|//|/\*|\*/', value):
            reject('Remove external resources, scripts and embedded files from SVG images.')
        found = []
        def local(match):
            target = match.group(1).strip().strip('\"\'')
            if not re.fullmatch('#' + IDENTIFIER, target):
                reject('SVG images may reference only definitions in the same image.')
            found.append(target[1:])
            return ''
        remainder = re.sub(r'url\s*\(([^()]*)\)', local, value, flags=re.I)
        if re.search(r'url\s*\(', remainder, re.I):
            reject()
        for token in re.finditer(r'[A-Za-z_-][A-Za-z0-9_-]*', remainder):
            position = token.end()
            while position < len(remainder) and remainder[position].isspace():
                position += 1
            if position < len(remainder) and remainder[position] == '(' and token[0].lower() not in {'rgb', 'rgba', 'hsl', 'hsla', 'matrix', 'translate', 'scale', 'rotate', 'skewx', 'skewy'}:
                reject('An SVG uses an unsupported style function.')
        return found

    def declarations(text):
        refs = []
        for declaration in text.split(';'):
            if not declaration.strip():
                continue
            key, separator, value = declaration.partition(':')
            if not separator or key.strip().lower() not in PROPERTIES or not value.strip():
                reject('An SVG uses an unsupported style property.')
            refs.extend(value_refs(value))
        return refs

    stack = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        nodes.append(node)
        budget['nodes'] += 1
        if len(nodes) > 20000 or budget['nodes'] > 250000 or depth > 32 or len(node.attrib) > 64:
            reject('SVG images exceed the supported complexity budget.')
        if node.tag not in ELEMENTS:
            reject()
        refs = references.setdefault(node, [])
        for key, value in node.attrib.items():
            if key in (XML + 'space', XML + 'lang'):
                continue
            local = key[len(XLINK):] if key.startswith(XLINK) else key
            if local not in ATTRS or len(value) > 200000:
                reject()
            if local == 'id':
                if not re.fullmatch(IDENTIFIER, value) or value in identifiers:
                    reject('An SVG contains duplicate or unsupported definition identifiers.')
                identifiers[value] = node
            elif local == 'href':
                if node.tag not in {SVG + x for x in ('use', 'linearGradient', 'radialGradient', 'textPath')} or not re.fullmatch('#' + IDENTIFIER, value):
                    reject('SVG images may reference only definitions in the same image.')
                refs.append(value[1:])
            elif local == 'style':
                refs.extend(declarations(value))
            else:
                refs.extend(value_refs(value))
        if node.tag == SVG + 'style':
            if len(node):
                reject()
            css = node.text or ''
            if len(css) > 65536:
                reject('An SVG stylesheet exceeds the supported budget.')
            # Linear comment/rule scanning also bounds malformed stylesheets.
            parts, cursor = [], 0
            while True:
                start = css.find('/*', cursor)
                if start < 0:
                    parts.append(css[cursor:])
                    break
                end = css.find('*/', start + 2)
                if end < 0:
                    reject('An SVG uses an incomplete stylesheet.')
                parts.append(css[cursor:start])
                cursor = end + 2
            css = ''.join(parts)
            value_refs(css)
            cursor = 0
            while css[cursor:].strip():
                start = css.find('{', cursor)
                end = css.find('}', start + 1) if start >= 0 else -1
                if start < 0 or end < 0 or not re.fullmatch(r'[A-Za-z0-9_.#,\s>*:+~-]{1,1024}', css[cursor:start]):
                    reject('An SVG uses an unsupported stylesheet.')
                if '{' in css[start + 1:end]:
                    reject('An SVG uses an unsupported stylesheet.')
                refs.extend(declarations(css[start + 1:end]))
                cursor = end + 1
        stack.extend((child, depth + 1) for child in node)

    # Count the expanded DOM/reference graph, not just serialized XML nodes.
    active, memo = set(), {}
    def expansion(node, depth=0):
        if node in active or depth > 64:
            reject('An SVG contains circular or deeply nested references.')
        if node in memo:
            size, height = memo[node]
            if depth + height > 64:
                reject('An SVG contains circular or deeply nested references.')
            return size, height
        active.add(node)
        targets = list(node)
        for identifier in references[node]:
            if identifier not in identifiers:
                reject('An SVG refers to a missing internal definition.')
            targets.append(identifiers[identifier])
        size, height = 1, 0
        for target in targets:
            child_size, child_height = expansion(target, depth + 1)
            size += child_size
            height = max(height, child_height + 1)
            if size > 100000:
                reject('SVG references exceed the supported expansion budget.')
        if depth + height > 64:
            reject('An SVG contains circular or deeply nested references.')
        active.remove(node)
        memo[node] = size, height
        return size, height
    expansion(root)

    view = root.get('viewBox')
    dimensions = [300., 150.]
    if view is not None:
        parts = re.split(r'[\s,]+', view.strip())
        if len(parts) != 4 or any(not re.fullmatch(NUMBER, part) for part in parts):
            reject('An SVG has an invalid viewBox.')
        values = list(map(float, parts))
        if not all(math.isfinite(n) and abs(n) <= 1000000 for n in values) or min(values[2:]) <= 0:
            reject('An SVG has an invalid viewBox.')
        dimensions = values[2:]
    units = {'': 1, 'px': 1, 'pt': 96 / 72, 'pc': 16, 'in': 96, 'cm': 96 / 2.54, 'mm': 96 / 25.4}
    for index, key in enumerate(('width', 'height')):
        if root.get(key) is None:
            continue
        match = re.fullmatch('(' + NUMBER + r')(px|pt|pc|in|cm|mm|%)?', root.get(key).strip())
        if not match:
            reject('An SVG has an unsupported image size.')
        number = float(match[1])
        if not math.isfinite(number) or number <= 0 or number > 1000000:
            reject('An SVG has an unsupported image size.')
        if match[2] != '%':
            dimensions[index] = number * units[match[2] or '']
    pixels = math.ceil(dimensions[0]) * math.ceil(dimensions[1])
    budget['pixels'] += pixels
    if max(dimensions) > 16384 or pixels > 40000000 or budget['pixels'] > 160000000:
        reject('SVG images exceed the supported image budget.')
