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
    def test_malformed_xml_has_a_specific_non_content_error(self):
        with self.assertRaises(Rejected) as caught:inspect_docx(self.package('<w:p>'))
        self.assertEqual(caught.exception.code,'MALFORMED_XML')
        self.assertIn('save a new DOCX copy',str(caught.exception))
        self.assertNotIn('<w:p>',str(caught.exception))
    def test_revision_and_hidden(self):
        for tag in ['ins', 'del', 'vanish', 'commentRangeStart', 'altChunk', 'object']:
            with self.subTest(tag=tag), self.assertRaises(Rejected): inspect_docx(self.package(f'<w:{tag}/>'))
    def test_web_hidden_does_not_hide_printed_text(self):
        for value in ['', ' w:val="true"', ' w:val="false"']:
            body=f'<w:p><w:r><w:rPr><w:webHidden{value}/></w:rPr><w:t>Synthetic contents page</w:t></w:r></w:p>'
            with self.subTest(value=value): self.assertTrue(inspect_docx(self.package(body)))
    def test_explicitly_disabled_hidden_text_in_body_and_styles(self):
        for value in ['0', 'false', 'off']:
            with self.subTest(value=value):
                prop=f'<w:vanish w:val="{value}"/>'
                body=f'<w:p><w:r><w:rPr>{prop}</w:rPr><w:t>Visible synthetic text</w:t></w:r></w:p>'
                styles='<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:styleId="Normal"><w:rPr>'+prop+'</w:rPr></w:style></w:styles>'
                self.assertTrue(inspect_docx(self.package(body, {'word/styles.xml':styles})))
    def test_active_or_unknown_hidden_state_remains_rejected(self):
        for value in ['', ' w:val="true"', ' w:val="1"', ' w:val="on"', ' w:val="unknown"']:
            with self.subTest(value=value), self.assertRaises(Rejected) as caught:
                inspect_docx(self.package(f'<w:p><w:r><w:rPr><w:vanish{value}/><w:webHidden/></w:rPr><w:t>Synthetic hidden</w:t></w:r></w:p>'))
            self.assertEqual(caught.exception.code,'HIDDEN_TEXT')
    def test_disabled_run_does_not_bypass_hidden_style_or_defaults(self):
        for root in ['<w:docDefaults><w:rPrDefault><w:rPr><w:vanish/></w:rPr></w:rPrDefault></w:docDefaults>', '<w:style w:styleId="Base"><w:rPr><w:vanish/></w:rPr></w:style>']:
            styles='<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'+root+'</w:styles>'
            with self.subTest(root=root), self.assertRaises(Rejected) as caught:
                inspect_docx(self.package('<w:p><w:r><w:rPr><w:vanish w:val="false"/></w:rPr><w:t>Synthetic</w:t></w:r></w:p>', {'word/styles.xml':styles}))
            self.assertEqual(caught.exception.code,'HIDDEN_TEXT')
    def test_formatting_revisions_and_comment_markers_have_specific_reasons(self):
        for tag in ['pPrChange','rPrChange','tblPrChange','tblGridChange','tcPrChange','sectPrChange','moveToRangeStart','delText']:
            with self.subTest(tag=tag), self.assertRaises(Rejected) as caught:
                inspect_docx(self.package(f'<w:p><w:{tag}/><w:r><w:t>Synthetic</w:t></w:r></w:p>'))
            self.assertEqual(caught.exception.code,'TRACKED_CHANGES')
        for tag in ['comment','commentReference','commentRangeStart','commentRangeEnd']:
            with self.subTest(tag=tag), self.assertRaises(Rejected) as caught:
                inspect_docx(self.package(f'<w:p><w:{tag}/><w:r><w:t>Synthetic</w:t></w:r></w:p>'))
            self.assertEqual(caught.exception.code,'COMMENTS')
    def test_all_policy_reasons_are_reported_without_private_values(self):
        body='<w:p><w:ins><w:r><w:t>PRIVATE_SENTINEL</w:t></w:r></w:ins><w:commentRangeStart/><w:r><w:rPr><w:vanish/></w:rPr></w:r></w:p>'
        with self.assertRaises(Rejected) as caught:
            inspect_docx(self.package(body,{'word/fonts/sentinel.odttf':'private bytes','word/embeddings/sentinel.bin':'private bytes'}))
        self.assertEqual([r['code'] for r in caught.exception.reasons],['TRACKED_CHANGES','COMMENTS','HIDDEN_TEXT','EMBEDDED_OBJECTS','EMBEDDED_FONTS'])
        message=str(caught.exception)
        self.assertIn('tracked changes',message)
        self.assertIn('comments',message)
        self.assertIn('embedded fonts',message)
        self.assertNotIn('SENTINEL',message)
        self.assertNotIn('sentinel',message)
    def test_custom_xml_local_names_are_not_word_revisions(self):
        extra={'customXml/item1.xml':'<x:record xmlns:x="urn:synthetic"><x:ins/><x:del/><x:vanish/></x:record>'}
        self.assertTrue(inspect_docx(self.package(extra=extra)))
    def test_drawing_geometry_move_is_not_a_tracked_text_move(self):
        body='<w:p><w:r><w:t>Synthetic drawing</w:t><w:drawing xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:path><a:moveTo><a:pt x="0" y="0"/></a:moveTo></a:path></w:drawing></w:r></w:p>'
        self.assertTrue(inspect_docx(self.package(body)))
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
