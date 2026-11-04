import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import struct
import subprocess
import sys
import zlib
from xml.etree import ElementTree as ET
from preflight import prepare, Rejected, S
from table_styles import materialize

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

    def test_office_runner_loads_excel_dependencies_from_another_directory(self):
        directory = str(Path(__file__).resolve().parents[1] / 'word')
        code = f'import sys;sys.path.insert(0,{directory!r});import runner;runner.load_excel_preflight().prepare({str(self.source)!r},{str(self.output)!r},{{"sheets":[0]}})'
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.output.exists())

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

    def test_common_formatting_and_filters_are_preserved(self):
        xml = self.parts['xl/worksheets/sheet1.xml'].replace('</sheetData>', '</sheetData><autoFilter ref="A1:B8"/><conditionalFormatting sqref="B2:B8"><cfRule type="cellIs" operator="greaterThan" priority="1"><formula>5</formula></cfRule></conditionalFormatting>')
        self.rewrite(**{'xl/worksheets/sheet1.xml': xml})
        warnings = self.run_prepare()
        self.assertTrue(any('Conditional formatting' in w for w in warnings))
        self.assertTrue(any('filter' in w for w in warnings))
        with zipfile.ZipFile(self.output) as package:
            self.assertEqual(package.read('xl/worksheets/sheet1.xml'), xml.encode())
        self.rewrite(**{'xl/worksheets/sheet1.xml': xml.replace('<formula>5</formula>', '<formula>WEBSERVICE("https://example.invalid")</formula>')})
        with self.assertRaises(Rejected): self.run_prepare()

    def test_embedded_images_have_dimensions_and_total_budget(self):
        def png(width, height):
            def chunk(tag, data):
                return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
            return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b'')
        self.rewrite(**{'xl/media/synthetic.png': png(1, 1)})
        self.assertTrue(any('picture' in w for w in self.run_prepare()))
        for content in [b'not a png', png(20001, 1), png(5000, 5000)]:
            self.rewrite(**{'xl/media/synthetic.png': content})
            with self.assertRaises(Rejected): self.run_prepare()

    def test_charts_and_their_dependencies(self):
        chart = f'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart><c:plotArea><c:barChart/></c:plotArea></c:chart></c:chartSpace>'
        self.rewrite(**{'xl/charts/chart1.xml': chart, 'xl/drawings/_rels/drawing1.xml.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="chart1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/></Relationships>'})
        self.assertTrue(any('chart labels' in w for w in self.run_prepare()))
        self.rewrite(**{'xl/charts/chart1.xml': chart.replace('barChart', 'unknownChart')})
        with self.assertRaisesRegex(Rejected, 'chart type'): self.run_prepare()
        self.rewrite(**{'xl/charts/chart1.xml': chart, 'xl/drawings/_rels/drawing1.xml.rels': '<Relationships><Relationship Target="../charts/missing.xml"/></Relationships>'})
        with self.assertRaisesRegex(Rejected, 'missing'): self.run_prepare()
        self.rewrite(**{'xl/drawings/_rels/drawing1.xml.rels': '<Relationships><Relationship Type="image" Target="https://example.invalid/image.png" TargetMode="External"/></Relationships>'})
        with self.assertRaisesRegex(Rejected, 'Externally linked'): self.run_prepare()

    def test_all_sixty_standard_table_styles_preserve_values_and_direct_formatting(self):
        catalog = ET.parse(Path(__file__).with_name('table-styles.xml')).getroot()
        self.assertEqual(len(catalog), 60)
        for preset in catalog:
            with self.subTest(style=preset.tag):
                styles = ET.fromstring(f'<styleSheet xmlns="{S}"><fonts count="1"><font><name val="Arial"/><sz val="11"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFF0000"/></patternFill></fill></fills><borders count="1"><border/></borders><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" numFmtId="4"/><xf fontId="0" fillId="2" borderId="0" numFmtId="4"/></cellXfs></styleSheet>')
                sheet = ET.fromstring(f'<worksheet xmlns="{S}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Header</t></is></c><c r="B1"/></row><row r="2" hidden="1"><c r="A2" s="1"><f>SUM(1,2)</f><v>3</v></c><c r="B2"><v>5</v></c></row></sheetData></worksheet>')
                table = ET.fromstring(f'<table xmlns="{S}" ref="A1:B2"><tableStyleInfo name="{preset.tag}" showRowStripes="1"/></table>')
                materialize(styles, sheet, [table])
                cell = sheet.find(f'.//{{{S}}}c[@r="A2"]')
                xf = styles.find(f'{{{S}}}cellXfs')[int(cell.get('s'))]
                self.assertEqual(cell.find(f'{{{S}}}v').text, '3')
                self.assertEqual(cell.find(f'{{{S}}}f').text, 'SUM(1,2)')
                self.assertEqual(xf.get('numFmtId'), '4')
                self.assertEqual(sheet.find(f'.//{{{S}}}row[@r="2"]').get('hidden'), '1')
                self.assertIn(b'FFFF0000', ET.tostring(styles.find(f'{{{S}}}fills')[int(xf.get('fillId'))]))
                if preset.tag == 'TableStyleMedium2':
                    header = sheet.find(f'.//{{{S}}}c[@r="A1"]')
                    header_xf = styles.find(f'{{{S}}}cellXfs')[int(header.get('s'))]
                    self.assertIn(b'theme="4"', ET.tostring(styles.find(f'{{{S}}}fills')[int(header_xf.get('fillId'))]))

if __name__ == '__main__': unittest.main()
