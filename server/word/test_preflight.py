import tempfile
import unittest
import zipfile
from pathlib import Path
from preflight import inspect_docx, Rejected

class PreflightTests(unittest.TestCase):
    def package(self, body='<w:p><w:r><w:t>合成 Synthetic</w:t></w:r></w:p>', extra=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'test.docx'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', '<Types><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '</w:body></w:document>')
            for name, value in (extra or {}).items(): z.writestr(name, value)
        return path
    def test_regular(self):
        self.assertTrue(inspect_docx(self.package()))
    def test_empty(self):
        with self.assertRaises(Rejected): inspect_docx(self.package(''))
    def test_revision_and_hidden(self):
        for tag in ['ins', 'del', 'vanish', 'commentRangeStart', 'altChunk', 'object']:
            with self.subTest(tag=tag), self.assertRaises(Rejected): inspect_docx(self.package(f'<w:{tag}/>'))
    def test_external_resources(self):
        for kind, target in [('image', 'https://example.invalid/image'), ('hyperlink', 'file:///etc/passwd'), ('attachedTemplate', 'https://example.invalid/template')]:
            xml = f'<Relationships><Relationship TargetMode="External" Type="urn:test/{kind}" Target="{target}"/></Relationships>'
            with self.subTest(kind=kind), self.assertRaises(Rejected): inspect_docx(self.package(extra={'word/_rels/document.xml.rels': xml}))
    def test_plain_link_allowed(self):
        inspect_docx(self.package(extra={'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Type="urn:test/hyperlink" Target="https://example.invalid/"/></Relationships>'}))
    def test_unsafe_package(self):
        for name, value in [('../bad.xml', '<x/>'), ('word/vbaProject.bin', 'macro'), ('word/embeddings/object.bin', 'object'), ('word/fonts/font.odttf', 'font'), ('word/bomb.xml', '<!DOCTYPE x [<!ENTITY x "x">]><x/>'), ('word/large.bin', 'x' * 100000)]:
            with self.subTest(name=name), self.assertRaises(Rejected): inspect_docx(self.package(extra={name: value}))
    def test_external_field(self):
        with self.assertRaises(Rejected): inspect_docx(self.package('<w:p><w:r><w:instrText>DDEAUTO example</w:instrText></w:r></w:p>'))
        with self.assertRaises(Rejected): inspect_docx(self.package('<w:p><w:r><w:instrText>DDE</w:instrText></w:r><w:r><w:instrText>AUTO example</w:instrText></w:r></w:p>'))

if __name__ == '__main__': unittest.main()
