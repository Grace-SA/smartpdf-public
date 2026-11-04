import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET
from preflight import prepare, Rejected, S

spec = importlib.util.spec_from_file_location('fixtures', Path(__file__).resolve().parents[2] / 'scripts/excel/fixtures.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

class Inspection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'input.xlsx'
        self.output = Path(self.temp.name) / 'prepared.xlsx'
        self.parts = fixtures.workbook(self.source)

    def rewrite(self, **parts):
        self.parts.update(parts)
        with zipfile.ZipFile(self.source, 'w', zipfile.ZIP_DEFLATED) as package:
            for name, content in self.parts.items(): package.writestr(name, content)

    def run_prepare(self, **settings):
        return prepare(self.source, self.output, {'sheets': [0], **settings})

    def test_selection_preserves_dependency_sheet_data(self):
        original = self.source.read_bytes()
        self.run_prepare()
        self.assertEqual(self.source.read_bytes(), original)
        with zipfile.ZipFile(self.output) as package:
            sheets = ET.fromstring(package.read('xl/workbook.xml')).findall(f'{{{S}}}sheets/{{{S}}}sheet')
            self.assertEqual([e.get('state') for e in sheets], ['visible', 'hidden', 'hidden'])
            self.assertEqual(package.read('xl/worksheets/sheet2.xml'), self.parts['xl/worksheets/sheet2.xml'].encode())

    def test_hidden_sheet_cannot_be_selected(self):
        with self.assertRaises(Rejected): self.run_prepare(sheets=[2])

    def test_bad_settings(self):
        for settings in [{'sheets': []}, {'sheets': [0, 0]}, {'sheets': [True]}, {'sheets': [-1]}, {'sheets': [3]}, {'scale': 'singlePageSheets'}, {'orientation': 'auto'}, {'url': 'https://example.invalid'}]:
            with self.subTest(settings=settings), self.assertRaises(Rejected): self.run_prepare(**settings)

    def test_fit_width_has_unbounded_vertical_pages_and_retains_print_area(self):
        fixtures.workbook(self.source, area='$A$1:$C$5')
        self.run_prepare(scale='width', orientation='landscape', paper='Letter')
        with zipfile.ZipFile(self.output) as package:
            tree = ET.fromstring(package.read('xl/worksheets/sheet1.xml'))
            setup = tree.find(f'{{{S}}}pageSetup')
            self.assertEqual(setup.get('fitToWidth'), '1')
            self.assertEqual(setup.get('fitToHeight'), '0')
            self.assertEqual(setup.get('paperSize'), '1')
            self.assertEqual(setup.get('orientation'), 'landscape')
            self.assertIn(b'$A$1:$C$5', package.read('xl/workbook.xml'))
            self.assertEqual(package.read('xl/worksheets/sheet2.xml'), self.parts['xl/worksheets/sheet2.xml'].encode())

    def test_page_scale_warns(self):
        self.assertTrue(any('very small' in w for w in self.run_prepare(scale='page')))

    def test_overlapping_columns_refused_without_losing_valid_hidden_columns(self):
        original = self.parts['xl/worksheets/sheet1.xml']
        self.rewrite(**{'xl/worksheets/sheet1.xml': original.replace('<cols>', '<cols><col min="2" max="2" hidden="1"/>')})
        with self.assertRaisesRegex(Rejected, 'Overlapping'): self.run_prepare()
        self.rewrite(**{'xl/worksheets/sheet1.xml': original.replace('<col min="1" max="5" width="22" customWidth="1"/>', '<col min="1" max="1" width="22"/><col min="2" max="2" width="22" hidden="1"/><col min="3" max="5" width="22"/>')})
        self.run_prepare(scale='width')

    def test_package_hazards(self):
        for name, value in [('xl/vbaProject.bin', 'x'), ('../escape.xml', '<x/>'), ('xl/connections.xml', '<x/>'), ('_xmlsignatures/sig1.xml', '<x/>'), ('xl/metadata.xml', '<x/>'), ('xl/unknown.bin', 'x')]:
            with self.subTest(name=name):
                fixtures.workbook(self.source)
                with zipfile.ZipFile(self.source, 'a') as package: package.writestr(name, value)
                with self.assertRaises(Rejected): self.run_prepare()

    def test_duplicate_and_corrupt_zip(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(self.source, 'a') as package: package.writestr('xl/workbook.xml', '<x/>')
        with self.assertRaises(Rejected): self.run_prepare()
        self.source.write_bytes(b'not a workbook')
        with self.assertRaises(Rejected): self.run_prepare()

    def test_xml_and_external_relationships(self):
        for xml in ['<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><x/>', '<x>', '<x><externalReference/></x>', '<x><oleObject/></x>', '<x><extLst/></x>', '<x><chart/></x>', '<x><drawing/></x>', '<x><conditionalFormatting/></x>', '<x><autoFilter/></x>']:
            with self.subTest(xml=xml):
                self.parts = fixtures.workbook(self.source)
                self.rewrite(**{'xl/worksheets/sheet1.xml': xml})
                with self.assertRaises(Rejected): self.run_prepare()
        self.parts = fixtures.workbook(self.source)
        self.rewrite(**{'xl/_rels/workbook.xml.rels': '<Relationships><Relationship Id="rId1" Type="worksheet" Target="https://example.invalid/data" TargetMode="External"/></Relationships>'})
        with self.assertRaises(Rejected): self.run_prepare()

    def test_formula_allowlist_and_cache(self):
        self.parts = fixtures.workbook(self.source, formula=True)
        self.assertTrue(any('recalculated' in w for w in self.run_prepare()))
        for formula in ['NOW()', 'WEBSERVICE("https://example.invalid")', '[other.xlsx]Sheet1!A1', 'XLOOKUP(1,A1:A2,B1:B2)', 'SUM(1,2)|DDE']:
            self.parts = fixtures.workbook(self.source, formula=True)
            self.rewrite(**{'xl/worksheets/sheet1.xml': self.parts['xl/worksheets/sheet1.xml'].replace('SUM(1,2)', formula.replace('&', '&amp;').replace('<', '&lt;'))})
            with self.subTest(formula=formula), self.assertRaises(Rejected): self.run_prepare()
        self.parts = fixtures.workbook(self.source, formula=True)
        self.rewrite(**{'xl/worksheets/sheet1.xml': self.parts['xl/worksheets/sheet1.xml'].replace('<v>3</v>', '')})
        with self.assertRaises(Rejected): self.run_prepare()

    def test_known_excel_metadata_preserves_prefix_declarations(self):
        xml = self.parts['xl/workbook.xml'].replace('<workbook ', '<workbook xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:x15="http://schemas.microsoft.com/office/spreadsheetml/2010/11/main" mc:Ignorable="x15" ')
        xml = xml.replace('</workbook>', '<extLst><ext uri="{140A7094-0E35-4892-8432-C4D2E57EDEB5}"><x15:workbookPr chartTrackingRefBase="1"/></ext></extLst></workbook>')
        self.rewrite(**{'xl/workbook.xml': xml})
        self.run_prepare()
        with zipfile.ZipFile(self.output) as package:
            output = package.read('xl/workbook.xml')
            self.assertIn(b'xmlns:x15=', output)
            ET.fromstring(output)
        unsupported = xml.replace('<x15:workbookPr chartTrackingRefBase="1"/>', '<x15:workbookPr chartTrackingRefBase="1"><x15:unsupported/></x15:workbookPr>')
        ET.fromstring(unsupported)
        self.rewrite(**{'xl/workbook.xml': unsupported})
        with self.assertRaisesRegex(Rejected, 'unsupported extensions'): self.run_prepare()

    def test_opaque_printer_settings_removed_but_portable_page_settings_remain(self):
        self.parts['[Content_Types].xml'] = self.parts['[Content_Types].xml'].replace('</Types>', '<Default Extension="bin" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.printerSettings"/></Types>')
        self.parts['xl/worksheets/sheet1.xml'] = self.parts['xl/worksheets/sheet1.xml'].replace('<worksheet ', '<worksheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ').replace('paperSize="9"', 'paperSize="9" r:id="printer1"')
        self.rewrite(**{'xl/printerSettings/printerSettings1.bin': b'synthetic-opaque-driver-data', 'xl/worksheets/_rels/sheet1.xml.rels': '<Relationships><Relationship Id="printer1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/printerSettings" Target="../printerSettings/printerSettings1.bin"/></Relationships>'})
        self.run_prepare()
        with zipfile.ZipFile(self.output) as package:
            self.assertNotIn('xl/printerSettings/printerSettings1.bin', package.namelist())
            self.assertNotIn(b'printer1', package.read('xl/worksheets/sheet1.xml'))
            self.assertIn(b'paperSize="9"', package.read('xl/worksheets/sheet1.xml'))

if __name__ == '__main__': unittest.main()
