"""No source margin may disappear or inherit across a table continuation."""
import copy,tempfile,unittest
from pathlib import Path
from docx import Document
from exporter import export_word
from layout import link_tables
from model import table_from_html
from worker import convert


def pages(margins):
    result=[]
    for i,footer in enumerate(margins):
        table=table_from_html('<table><tr><th>Item</th><th>Value</th></tr><tr><td>Row'+str(i)+'</td><td>'+str(100+i)+'</td></tr></table>')
        table.update(id='t'+str(i),kind='table',bbox=[40,50,570,740],widths=[1,1])
        blocks=[dict(id='h'+str(i),kind='header',bbox=[40,10,570,20],text='Inventory'),table]
        if footer is not None:blocks.append(dict(id='f'+str(i),kind='footer',bbox=[40,760,570,780],text=footer))
        result.append(dict(index=i,width=612,height=792,blocks=blocks))
    link_tables(result)
    return result

class ContinuationMargins(unittest.TestCase):
    def export(self,p):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name);before=copy.deepcopy(p)
        export_word(dict(schema=2,pages=p),root/'out.docx',root);self.assertEqual(p,before)
        return Document(root/'out.docx')
    def test_changed_margin_and_three_page_chain(self):
        doc=self.export(pages(['Reporting year 2023','Reporting year 2024','Reporting year 2024']))
        self.assertEqual(len(doc.tables),2);self.assertEqual(len(doc.sections),2)
        self.assertEqual([s.footer.paragraphs[0].text for s in doc.sections],['Reporting year 2023','Reporting year 2024'])
        text=lambda t:' '.join(c.text for r in t.rows for c in r.cells)
        self.assertIn('Row0',text(doc.tables[0]));self.assertNotIn('Row2',text(doc.tables[0]))
        self.assertIn('Row1',text(doc.tables[1]));self.assertIn('Row2',text(doc.tables[1]))
    def test_missing_new_and_identical_margins(self):
        for values,expected in [(['A',None],['A','']),([None,'B'],['','B']),(['A','A'],['A'])]:
            with self.subTest(values=values):
                doc=self.export(pages(values));self.assertEqual([s.footer.paragraphs[0].text for s in doc.sections],expected)
                self.assertEqual(len(doc.tables),len(expected))
    def test_returning_margin_and_removed_header(self):
        doc=self.export(pages(['A','B','A']))
        self.assertEqual(len(doc.tables),3)
        self.assertEqual([s.footer.paragraphs[0].text for s in doc.sections],['A','B','A'])
        p=pages([None,None]);p[1]['blocks']=[b for b in p[1]['blocks']if b['kind']!='header']
        doc=self.export(p)
        self.assertEqual(len(doc.tables),2)
        self.assertEqual([s.header.paragraphs[0].text for s in doc.sections],['Inventory',''])

    def test_changed_format_and_nonadjacent_reference(self):
        p=pages(['A','A']);p[1]['blocks'][0]['bold']=True
        self.assertEqual(len(self.export(p).tables),2)
        p=pages(['A','A','A']);p[1]['blocks'][1].pop('continues',None)
        self.assertEqual(len(self.export(p).tables),3)
    def test_real_native_pdf_retains_later_year(self):
        from reportlab.pdfgen.canvas import Canvas
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);source=root/'in.pdf';c=Canvas(str(source),pagesize=(612,792))
            for year in(2023,2024):
                c.setFont('Helvetica',12);c.drawString(50,760,'Inventory'+(' (continued)'if year==2024 else''))
                c.setFont('Helvetica',10);c.drawString(50,20,'Reporting year '+str(year))
                for x in(50,300,560):c.line(x,60,x,690)
                for n in range(22):c.line(50,690-n*30,560,690-n*30)
                for n in range(21):
                    c.drawString(60,670-n*30,'Item'if n==0 else str(n));c.drawString(310,670-n*30,'Value'if n==0 else str(year*100+n))
                c.showPage()
            c.save();convert(source,root/'out.docx');doc=Document(root/'out.docx')
            self.assertEqual(len(doc.tables),2)
            self.assertEqual([s.header.paragraphs[0].text for s in doc.sections],['Inventory','Inventory (continued)'])
            self.assertEqual([s.footer.paragraphs[0].text for s in doc.sections],['Reporting year 2023','Reporting year 2024'])
            for t,year in zip(doc.tables,(2023,2024)):
                self.assertEqual([r.cells[1].text for r in t.rows[1:]],[str(year*100+n)for n in range(1,21)])
if __name__=='__main__':unittest.main()
