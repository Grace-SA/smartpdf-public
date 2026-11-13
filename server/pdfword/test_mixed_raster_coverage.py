"""A native title must not hide tiled raster content from OCR routing."""
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfWriter, PdfReader
from pypdf.generic import NameObject, DictionaryObject, NumberObject, DecodedStreamObject
from unittest.mock import patch
from model import Rejected
from worker import raster_regions_need_ocr, convert
from test_worker import fixture


def tile_pdf(path):
    fixture(path, content=b'BT /F1 12 Tf 48 750 Td (Native title) Tj ET')
    reader=PdfReader(path);writer=PdfWriter();page=writer.add_page(reader.pages[0])
    image=DecodedStreamObject();image.set_data(bytes([0,0,0,255,255,255])*8)
    image.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
                  NameObject('/Width'):NumberObject(4),NameObject('/Height'):NumberObject(4),
                  NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
    page['/Resources'][NameObject('/XObject')]=DictionaryObject({NameObject('/Im'):writer._add_object(image)})
    stream=DecodedStreamObject();stream.set_data(page.get_contents().get_data()+b' q 540 0 0 320 36 62 cm /Im Do Q q 540 0 0 320 36 402 cm /Im Do Q')
    page[NameObject('/Contents')]=writer._add_object(stream)
    with path.open('wb') as out:writer.write(out)


class MixedRasterCoverageTests(unittest.TestCase):
    def test_multiple_regions_collectively_require_ocr(self):
        blocks=[dict(kind='image',bbox=[0,0,100,40]),dict(kind='image',bbox=[0,60,100,100])]
        self.assertTrue(raster_regions_need_ocr(blocks,100,100))

    def test_overlap_and_small_photos_do_not_inflate_coverage(self):
        self.assertFalse(raster_regions_need_ocr([dict(kind='image',bbox=[0,0,100,40])]*4,100,100))
        self.assertFalse(raster_regions_need_ocr([dict(kind='image',bbox=[0,0,20,20])],100,100))
        self.assertFalse(raster_regions_need_ocr([],100,100))

    def test_off_page_boxes_never_inflate_visible_coverage(self):
        for boxes in [[[-100,0,50,100],[-1000,0,-500,100]],
                      [[50,0,200,100],[500,0,1000,100]],
                      [[0,-100,100,50],[0,-1000,100,-500]],
                      [[0,50,100,200],[0,500,100,1000]]]:
            self.assertFalse(raster_regions_need_ocr([dict(kind='image',bbox=b) for b in boxes],100,100))

    def test_geometry_work_is_bounded(self):
        self.assertTrue(raster_regions_need_ocr([dict(kind='image',bbox=[0,0,1,1])]*513,100,100))

    def test_mixed_native_title_and_tiles_fail_closed_without_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.pdf';output=root/'out.docx';tile_pdf(source)
            with patch.dict('os.environ',{},clear=True):
                with self.assertRaisesRegex(Rejected,'OCR worker is not configured'):
                    convert(source,output)
            self.assertFalse(output.exists())

    def test_configured_adapter_is_called_and_warning_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.pdf';output=root/'out.docx';tile_pdf(source)
            result=[dict(kind='paragraph',bbox=[48,40,550,100],text='Recognized test text',source='test',size=12)]
            with patch('worker.OCR.recognize',return_value=result) as recognize:
                report=convert(source,output)
            recognize.assert_called_once()
            self.assertTrue(recognize.call_args.kwargs['complex_layout'])
            self.assertTrue(any('recognized with OCR' in w for w in report['warnings']))


if __name__ == '__main__':
    unittest.main()
