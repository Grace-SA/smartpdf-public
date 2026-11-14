"""Dollar amount markers are not implicit math delimiters."""
import tempfile,unittest,zipfile
from pathlib import Path
from lxml import etree
from math_export import segments,unsupported
from worker import convert

class CurrencyText(unittest.TestCase):
    def test_currency_operators_preserve_every_character(self):
        for value in ('Total $5+$10=$15.','Costs $5 + $10.',
                      'Fees $50 / month; deposit $100.',
                      '$1,234.50+$2,345.60', '$-5+$-10', '$−5+$−10', '$.50+$.25',
                      '$5+$10 + $20+$30.', 'Total $ 5 + $ 10 = $ 15.',
                      '$5+$\u00a010', '$5+$\u202f10', '$5+$\t10', '$ -5+$ −10'):
            with self.subTest(value=value):
                parts=list(segments(value))
                self.assertEqual(''.join(p[0]for p in parts),value)
                self.assertTrue(all(p[1]is None and not p[2]for p in parts))
                self.assertFalse(unsupported(value))
    def test_explicit_math_and_mixed_text_unchanged(self):
        for value in ('$5+10$',r'\(5+10\)','$$5+10$$',r'$x_i$', '$5+10$ units', '$5+10$ + 10', '$5+10$ end'):
            with self.subTest(value=value):self.assertTrue(any(p[1]is not None for p in segments(value)))
        for value in (r'$x_i$ costs $5+$10.',r'$5+$10 and $x_i$'):
            parts=list(segments(value));self.assertEqual(''.join(p[0]for p in parts),value)
            self.assertEqual(sum(p[1]is not None for p in parts),0)
            self.assertFalse(any(p[2]for p in parts))
        for value in (r'Total $5+$10=$15; math $x+1$.',
                      r'Total $5+$10=$15; tax $15 + total $20.'):
            parts=list(segments(value));self.assertEqual(''.join(p[0]for p in parts),value)
            self.assertTrue(all(p[1]is None and not p[2]for p in parts))
        for value in (r'Total $5+$10=$15; math \(x+1\).',
                      r'Total $5+$10=$15; math $$x+1$$.'):
            parts=list(segments(value));self.assertEqual(''.join(p[0]for p in parts),value)
            self.assertEqual(sum(p[1]is not None for p in parts),1)
            self.assertFalse(any(p[2]for p in parts))
        # No safe distinction between adjacent numeric math and currency:
        # preserve the complete literal rather than silently dropping symbols.
        for value in ('$5$10', '$5$ 10', '$5+5$ 10 units'):
            self.assertTrue(all(p[1]is None for p in segments(value)))
    def test_native_pdf_money_is_editable_and_exact(self):
        from reportlab.pdfgen.canvas import Canvas
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);source=root/'source.pdf';c=Canvas(str(source),pagesize=(612,792));c.setFont('Helvetica',12)
            values=['Total $5+$10=$15.','Balance $1,234.50+$2,345.60.',
                    'Total $ 5 + $ 10 = $ 15.', 'Total $5+$ 10=$ 15.']
            for i,s in enumerate(values):c.drawString(40,720-40*i,s)
            c.save();out=root/'out.docx';report=convert(source,out)
            self.assertEqual(report['images'],0)
            with zipfile.ZipFile(out)as z:
                tree=etree.fromstring(z.read('word/document.xml'))
                text=[''.join(p.xpath('.//*[local-name()="t"]/text()'))for p in tree.xpath('//*[local-name()="p"]')]
                self.assertEqual([t for t in text if t],values)
                self.assertFalse(tree.xpath('//*[local-name()="oMath"]'))
    def test_cross_style_currency_context_is_preserved(self):
        from exporter import export_word
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);value='Total $5+$10=$15.'
            blocks=[dict(id='p',kind='paragraph',bbox=[40,40,550,80],text=value,
                         runs=[dict(text='Total $5+$',bold=False),dict(text='10',bold=True),dict(text='=$15.',italic=True)])]
            out=root/'out.docx';export_word(dict(schema=2,pages=[dict(index=0,width=612,height=792,blocks=blocks)]),out,root)
            from docx import Document
            doc=Document(out);self.assertEqual(doc.paragraphs[0].text,value)
            self.assertTrue(any(r.bold and r.text=='10'for r in doc.paragraphs[0].runs))
            self.assertFalse(doc.element.xpath('//*[local-name()="oMath"]'))
    def test_run_boundaries_and_paragraph_scope(self):
        from exporter import export_word
        from docx import Document
        cases=[['Total $5+$','10','=','$15.'],
               ['$', '-5', '+', '$', '-10'],
               ['$', '5', '+$', '10', '=$', '15; math ', '$x_i$'],
               [r'Math \(x+1\); $5+$','10.']]
        for parts in cases:
            with self.subTest(parts=parts),tempfile.TemporaryDirectory()as temp:
                root=Path(temp);value=''.join(parts)
                runs=[dict(text=t,bold=i%2==0,size=10+i)for i,t in enumerate(parts)]
                blocks=[dict(id='a',kind='paragraph',bbox=[40,40,550,80],text=value,runs=runs),
                        dict(id='b',kind='paragraph',bbox=[40,100,550,130],text='$x_i$'),
                        dict(id='c',kind='paragraph',bbox=[40,150,550,170],text='$5+'),
                        dict(id='d',kind='paragraph',bbox=[40,190,550,210],text='$10')]
                out=root/'out.docx';export_word(dict(schema=2,pages=[dict(index=0,width=612,height=792,blocks=blocks)]),out,root);doc=Document(out)
                explicit=parts[0].startswith('Math')
                if not explicit:
                    self.assertEqual(doc.paragraphs[0].text,value)
                    for actual,expected in zip(doc.paragraphs[0].runs,runs):
                        self.assertEqual(actual.text,expected['text']);self.assertEqual(actual.bold,expected['bold']);self.assertEqual(actual.font.size.pt,expected['size'])
                else:self.assertIn('$5+$10.',doc.paragraphs[0].text)
                self.assertEqual(len(doc.element.xpath('//*[local-name()="oMath"]')),2 if explicit else 1)
                self.assertEqual([p.text for p in doc.paragraphs[2:]],['$5+','$10'])
    def test_table_cells_do_not_share_currency_state(self):
        from model import table_from_html
        from exporter import export_word
        from docx import Document
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);table=table_from_html('<table><tr><td>$5+$10</td><td>$x_i$</td></tr><tr><td>$5+</td><td>$10</td></tr></table>')
            table.update(id='t',kind='table',bbox=[40,40,550,200])
            out=root/'out.docx';export_word(dict(schema=2,pages=[dict(index=0,width=612,height=792,blocks=[table])]),out,root)
            doc=Document(out);t=doc.tables[0]
            self.assertEqual(t.cell(0,0).text,'$5+$10');self.assertEqual(t.cell(1,0).text,'$5+');self.assertEqual(t.cell(1,1).text,'$10')
            self.assertEqual(len(doc.element.xpath('//*[local-name()="oMath"]')),1)
if __name__=='__main__':unittest.main()
