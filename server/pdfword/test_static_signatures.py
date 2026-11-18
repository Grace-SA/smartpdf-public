import hashlib
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfWriter, PdfReader
from pypdf.generic import (DictionaryObject, NameObject, NumberObject, ArrayObject,
                           DecodedStreamObject, TextStringObject, BooleanObject)
from static_signatures import flatten_signatures, signature_widgets
from worker import preflight
from model import Rejected


class SignatureTests(unittest.TestCase):
    def fixture(self, path, field_type='/Sig', readonly=True, appearance=True, action=False):
        writer=PdfWriter();page=writer.add_blank_page(width=612,height=792)
        field=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),
            NameObject('/Subtype'):NameObject('/Widget'),NameObject('/FT'):NameObject(field_type),
            NameObject('/Ff'):NumberObject(int(readonly)),NameObject('/F'):NumberObject(4),
            NameObject('/T'):TextStringObject('Synthetic signature'),
            NameObject('/Rect'):ArrayObject([NumberObject(v) for v in (20,700,100,720)]),
            NameObject('/V'):DictionaryObject({NameObject('/Type'):NameObject('/Sig')})})
        if appearance:
            stream=DecodedStreamObject();stream.set_data(b'0 0 1 rg 0 0 80 20 re f')
            stream.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
                NameObject('/BBox'):ArrayObject([NumberObject(v) for v in (0,0,80,20)]),NameObject('/Resources'):DictionaryObject()})
            field[NameObject('/AP')]=DictionaryObject({NameObject('/N'):writer._add_object(stream)})
        if action:field[NameObject('/AA')]=DictionaryObject()
        ref=writer._add_object(field);page[NameObject('/Annots')]=ArrayObject([ref])
        writer._root_object[NameObject('/AcroForm')]=DictionaryObject({NameObject('/Fields'):ArrayObject([ref])})
        writer.write(path)

    def test_static_appearance_is_preserved_without_changing_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.pdf';self.fixture(source)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(preflight(source),1)
            result,changed=flatten_signatures(source,root)
            self.assertTrue(changed);self.assertNotEqual(source,result)
            self.assertEqual(preflight(result),1)
            self.assertNotIn('/AcroForm',PdfReader(result).trailer['/Root'])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)

    def test_active_forms_and_missing_appearances_remain_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf'
            for options in ({'field_type':'/Tx'},{'readonly':False},{'appearance':False},{'action':True}):
                self.fixture(source,**options)
                with self.subTest(options=options):
                    self.assertFalse(signature_widgets(PdfReader(source)))
                    with self.assertRaises(Rejected):preflight(source)

    def test_plain_pdf_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'plain.pdf';w=PdfWriter();w.add_blank_page(width=612,height=792);w.write(source)
            self.assertEqual(flatten_signatures(source,tmp),(source,False))

    def test_hidden_or_incomplete_signature_catalog_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.pdf';target=root/'modified.pdf'
            for mode in ('hidden','missing-widget','xfa','appearance-regeneration','malformed-field'):
                self.fixture(source)
                writer=PdfWriter(clone_from=source)
                form=writer._root_object['/AcroForm'];field=form['/Fields'][0].get_object()
                if mode=='hidden':field[NameObject('/F')]=NumberObject(2)
                elif mode=='missing-widget':writer.pages[0].pop('/Annots')
                elif mode=='xfa':form[NameObject('/XFA')]=TextStringObject('synthetic')
                elif mode=='appearance-regeneration':form[NameObject('/NeedAppearances')]=BooleanObject(True)
                else:form[NameObject('/Fields')]=ArrayObject([NumberObject(7)])
                writer.write(target)
                with self.subTest(mode=mode),self.assertRaises(Rejected):preflight(target)
