import unittest
from svg_check import inspect_svg, SVGRejected


def svg(body='', attrs='viewBox="0 0 100 100"'):
    return f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" {attrs}>{body}</svg>'.encode()


class StaticSVGTests(unittest.TestCase):
    def check(self, raw):
        inspect_svg(raw, {'nodes': 0, 'pixels': 0})

    def test_static_shapes_css_and_internal_resources(self):
        self.check(svg('<style>.a{fill:url(#g);stroke:#fff;stroke-width:2}</style><defs><linearGradient id="g"><stop offset="0" stop-color="#f00"/><stop offset="1" stop-color="#00f"/></linearGradient><path id="p" d="M0 0 L100 100"/></defs><rect class="a" width="100" height="100"/><use xlink:href="#p"/><text x="5" y="20">Original synthetic text</text>'))

    def test_active_or_nested_documents(self):
        for body in ('<script/>', '<foreignObject/>', '<animate/>', '<set/>', '<image href="data:image/png;base64,AAAA"/>', '<iframe/>', '<filter/>'):
            with self.subTest(body=body), self.assertRaises(SVGRejected): self.check(svg(body))
        for attr in ('onload="alert(1)"', 'xml:base="file:///"', 'width="NaN"'):
            with self.subTest(attr=attr), self.assertRaises(SVGRejected): self.check(svg(attrs=attr))

    def test_external_links_and_css_obfuscation(self):
        for target in ('https://example.invalid/a.svg#p', 'file:///etc/passwd', 'data:image/svg+xml,x', '//example.invalid/x', '../other.svg#p'):
            with self.subTest(target=target), self.assertRaises(SVGRejected): self.check(svg(f'<use href="{target}"/>'))
        for css in ('@import "https://example.invalid/x";', '.a{fill:url(https://example.invalid/x)}', r'.a{fill:u\72l(file:///etc/passwd)}', '.a{fill:var(--remote)}', '.a{background:red}', '.a{fill:u/**/rl(https://example.invalid/x)}', '.a{fill:image("relative.svg")}', '.a{fill:image-set("relative.svg" 1x)}'):
            with self.subTest(css=css), self.assertRaises(SVGRejected): self.check(svg(f'<style>{css}</style>'))

    def test_missing_duplicate_and_circular_references(self):
        for body in ('<use href="#missing"/>', '<path id="x"/><path id="x"/>', '<g id="x"><use href="#x"/></g>', '<defs><linearGradient id="a" href="#b"/><linearGradient id="b" href="#a"/></defs>', '<style>.a{fill:url(#missing)}</style>'):
            with self.subTest(body=body), self.assertRaises(SVGRejected): self.check(svg(body))

    def test_reference_expansion(self):
        body = '<g id="n0"><path d="M0 0L1 1"/></g>'
        for index in range(1, 18): body += f'<g id="n{index}"><use href="#n{index-1}"/><use href="#n{index-1}"/></g>'
        with self.assertRaisesRegex(SVGRejected, 'expansion'): self.check(svg(body))
        body = '<path id="n0" d="M0 0L1 1"/>'
        for index in range(1, 70): body += f'<use id="n{index}" href="#n{index-1}"/>'
        with self.assertRaisesRegex(SVGRejected, 'deeply nested'): self.check(svg(body))

    def test_xml_encoding_entities_and_budgets(self):
        for raw in (svg().decode().encode('utf-16'), b'<!DOCTYPE svg [<!ENTITY x "x">]>' + svg(), b'<?xml-stylesheet href="file:///x"?>' + svg(), svg('<g>'*34+'</g>'*34), svg('<path/>'*20001), svg('x'*(4*1024**2))):
            with self.subTest(size=len(raw)), self.assertRaises(SVGRejected): self.check(raw)
        for attrs in ('viewBox="0 0 -1 100"', 'viewBox="0 0 1e999 10"', 'width="100000" height="100000"', 'width="10em"'):
            with self.subTest(attrs=attrs), self.assertRaises(SVGRejected): self.check(svg(attrs=attrs))
        with self.assertRaises(SVGRejected): inspect_svg(svg(), {'nodes': 250000, 'pixels': 0})
        with self.assertRaises(SVGRejected): inspect_svg(svg(), {'nodes': 0, 'pixels': 160000000})
        for css in ('a'*65536, '/*'*10000, 'a'*65537, '.a{fill:red}{fill:blue}', '.a{fill:red'):
            with self.subTest(size=len(css)), self.assertRaises(SVGRejected): self.check(svg(f'<style>{css}</style>'))


if __name__ == '__main__':
    unittest.main()
