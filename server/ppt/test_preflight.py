import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from preflight import inspect_pptx, Rejected
from synthetic import presentation, pack, PKG, R


class PresentationTests(unittest.TestCase):
    def check(self, data):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'input.pptx'
            path.write_bytes(data)
            return inspect_pptx(path)

    def files(self):
        with zipfile.ZipFile(io.BytesIO(presentation())) as package:
            return {name: package.read(name) for name in package.namelist()}

    def test_visible_scope_and_geometry(self):
        result = self.check(presentation())
        self.assertEqual((result['slides'], result['visible']), (3, 2))
        self.assertEqual((result['width'], result['height']), (960, 540))

    def test_four_three(self):
        result = self.check(presentation(width=9144000, height=6858000))
        self.assertEqual((result['width'], result['height']), (720, 540))

    def test_all_hidden(self):
        with self.assertRaisesRegex(Rejected, 'visible slides'):
            self.check(presentation([('hidden', True)]))

    def test_malformed_and_non_zip(self):
        for data in (b'', b'fake pptx', b'PK\x03\x04broken'):
            with self.subTest(data=data), self.assertRaises(Rejected):
                self.check(data)

    def test_macros_ole_fonts_and_media(self):
        for name in ('ppt/vbaProject.bin', 'ppt/activeX/object.xml', 'ppt/embeddings/oleObject1.bin', 'ppt/fonts/font.fntdata', 'ppt/media/movie.mp4'):
            files = self.files(); files[name] = b'not executable'
            with self.subTest(name=name), self.assertRaises(Rejected):
                self.check(pack(files))

    def test_external_relationships(self):
        for kind, target in (('image', 'https://example.invalid/image.png'), ('hyperlink', 'file:///etc/passwd'), ('hyperlink', 'javascript:alert(1)'), ('package', 'https://example.invalid/data.xlsx')):
            files = self.files()
            files['ppt/slides/_rels/slide1.xml.rels'] = f'<Relationships xmlns="{PKG}"><Relationship Id="ext" Type="{R}/{kind}" TargetMode="External" Target="{target}"/></Relationships>'
            with self.subTest(kind=kind, target=target), self.assertRaises(Rejected):
                self.check(pack(files))

    def test_static_web_link(self):
        files = self.files()
        files['ppt/slides/_rels/slide1.xml.rels'] = f'<Relationships xmlns="{PKG}"><Relationship Id="ext" Type="{R}/hyperlink" TargetMode="External" Target="https://example.invalid/"/></Relationships>'
        self.assertEqual(self.check(pack(files))['visible'], 2)

    def test_missing_slide(self):
        files = self.files(); del files['ppt/slides/slide1.xml']
        with self.assertRaises(Rejected): self.check(pack(files))

    def test_duplicate_slide_reference(self):
        files = self.files()
        files['ppt/presentation.xml'] = files['ppt/presentation.xml'].replace(b'r:id="rId2"', b'r:id="rId1"')
        with self.assertRaises(Rejected): self.check(pack(files))

    def test_unknown_hidden_state(self):
        files = self.files()
        files['ppt/slides/slide1.xml'] = files['ppt/slides/slide1.xml'].replace(b'show="1"', b'show="unknown"')
        with self.assertRaises(Rejected): self.check(pack(files))

    def test_entity_and_xml_depth(self):
        for xml in ('<!DOCTYPE x [<!ENTITY a "a">]><x/>', '<x>' * 70 + '</x>' * 70):
            files = self.files(); files['custom.xml'] = xml
            with self.subTest(xml=xml[:20]), self.assertRaises(Rejected): self.check(pack(files))

    def test_path_and_duplicates(self):
        for name in ('../outside.xml', '/absolute.xml', 'ppt/../outside.xml', 'ppt\\outside.xml'):
            files = self.files(); files[name] = '<x/>'
            data = pack(files)
            # Windows zipfile normalizes separators on write; patch both ZIP headers.
            if chr(92) in name:
                data = data.replace(name.replace(chr(92), '/').encode(), name.encode())
            with self.subTest(name=name), self.assertRaises(Rejected): self.check(data)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as package:
            package.writestr('x.xml', '<x/>'); package.writestr('x.xml', '<x/>')
        with self.assertRaises(Rejected): self.check(output.getvalue())

    def test_expansion_limit(self):
        files = self.files(); files['large.xml'] = '<x>' + 'x' * 1000000 + '</x>'
        with self.assertRaises(Rejected): self.check(pack(files))

    def test_image_pixel_limit(self):
        files = self.files(); files['ppt/media/image.png'] = b'\x89PNG\r\n\x1a\n' + b'\x00'*8 + (100000).to_bytes(4, 'big')*2
        with self.assertRaises(Rejected): self.check(pack(files))

    def test_visible_page_budget(self):
        with self.assertRaises(Rejected): self.check(presentation([('visible', False)]*201))


if __name__ == '__main__':
    unittest.main()
