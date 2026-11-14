import copy
import hashlib
import io
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pdfplumber
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader,PdfWriter
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server/pdf-to-excel'))
from scan_raster import resolution,raster_size,MAX_PIXELS
from convert import scan_tables,ConversionError


class ScanRasterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.n=0

    def fixture(self,size=(500,625),transform=None,overlay=False,alpha=False,two=False):
        self.n+=1;p=self.root/f'{self.n}.pdf'
        im=Image.new('RGB',size,'white');draw=ImageDraw.Draw(im)
        # Deliberately one native pixel thick; no native PDF lines/text.
        for x in [20,99,179,259,339,419,480]:draw.line((x,20,x,size[1]-20),fill='black',width=1)
        for y in [20,90,160,230,300,370,440,510,600]:
            if y<size[1]-1:draw.line((20,y,size[0]-20,y),fill='black',width=1)
        c=canvas.Canvas(str(p),pagesize=(240,300))
        if transform:c.transform(*transform)
        if alpha:c.setFillAlpha(.5)
        c.drawImage(ImageReader(im),0,0,width=240,height=300)
        if two:c.drawImage(ImageReader(im),0,0,width=240,height=300)
        if overlay:
            c.setFillColorRGB(1,1,1);c.rect(0,0,240,300,stroke=0,fill=1)
        c.save();return p,im

    def open(self,path):
        d=pdfplumber.open(path);self.addCleanup(d.close);return d.pages[0]

    def test_matches_native_dimensions_without_mutating_source(self):
        p,im=self.fixture();before=p.read_bytes();page=self.open(p)
        dpi=resolution(page);self.assertGreater(dpi,144);self.assertLess(dpi,151)
        rendered=page.to_image(resolution=dpi).original
        self.assertEqual(rendered.size,im.size)
        self.assertEqual(rendered.convert('RGB').tobytes(),im.tobytes())
        self.assertEqual(p.read_bytes(),before)

    def test_sampling_sizes_100_150_200_300_and_outside_cap(self):
        for dpi in (100,150,200,300,301):
            with self.subTest(dpi=dpi):
                size=(math.ceil(240*dpi/72),math.ceil(300*dpi/72))
                p,_=self.fixture(size=size);page=self.open(p);chosen=resolution(page)
                if dpi in (100,301):self.assertEqual(chosen,144)
                else:self.assertEqual(raster_size(page,chosen),size)

    def test_matrix_mirror_shear_subpixel_and_anisotropy_fallback(self):
        for matrix in [(-1,0,0,1,240,0),(1,.1,0,1,0,0),(1,0,0,1,.001,0),(1.01,0,0,1,0,0)]:
            with self.subTest(matrix=matrix):
                p,_=self.fixture(transform=matrix);self.assertEqual(resolution(self.open(p)),144)
        p,_=self.fixture(size=(500,700));self.assertEqual(resolution(self.open(p)),144)

    def test_multiple_images_and_transparency_fallback(self):
        for kw in ({'two':True},{'alpha':True}):
            p,_=self.fixture(**kw);self.assertEqual(resolution(self.open(p)),144)

    def test_rotated_or_cropped_fallback(self):
        p,_=self.fixture()
        for rotate in (True,False):
            reader=PdfReader(p);writer=PdfWriter();page=reader.pages[0]
            if rotate:page.rotate(90)
            else:page.cropbox.lower_left=(1,1)
            writer.add_page(page);out=self.root/f'modified-{rotate}.pdf'
            with out.open('wb') as f:writer.write(f)
            self.assertEqual(resolution(self.open(out)),144)

    def test_final_render_keeps_opaque_cover(self):
        p,im=self.fixture(overlay=True);page=self.open(p);dpi=resolution(page)
        self.assertGreater(dpi,144)
        rendered=page.to_image(resolution=dpi).original.convert('L')
        self.assertEqual(rendered.getextrema(),(255,255))
        fake=[([[30,30],[60,30],[60,50],[30,50]],'SECRET',.99)]
        with patch('convert._ocr',return_value=(fake,None)),patch('ocr_spaces.recover_spaces',return_value=fake):
            self.assertEqual(scan_tables(page),[])

    def test_native_dimensions_over_budget_fall_back(self):
        p,_=self.fixture();page=self.open(p)
        with patch.object(type(page),'images',new_callable=lambda:property(lambda p:[dict(x0=0,top=0,x1=p.width,bottom=p.height,srcsize=(10000,10000))])):
            self.assertEqual(resolution(page),144)

    def test_actual_ceil_budget_checked_before_render(self):
        page=SimpleNamespace(width=3333.4,height=1500,rotation=0,images=[],
                             bbox=(0,0,3333.4,1500),cropbox=(0,0,3333.4,1500),mediabox=(0,0,3333.4,1500))
        page.to_image=lambda **kw:self.fail('Oversize raster must not render')
        self.assertGreater(math.prod(raster_size(page,144)),MAX_PIXELS)
        with self.assertRaises(ConversionError):scan_tables(page)

    def test_fine_grid_and_physical_dimensions(self):
        p,_=self.fixture();page=self.open(p);dpi=resolution(page)
        fake=[([[35,35],[65,35],[65,55],[35,55]],'Field',.99)]
        with patch('convert._ocr',return_value=(fake,None)),patch('ocr_spaces.recover_spaces',return_value=fake):
            tables=scan_tables(page)
        self.assertEqual(len(tables),1)
        self.assertEqual((len(tables[0]['heights']),len(tables[0]['widths'])),(8,6))
        self.assertAlmostEqual(sum(tables[0]['widths']),460/(dpi/72),places=5)
        self.assertAlmostEqual(sum(tables[0]['heights']),580/(dpi/72),places=5)

    def test_render_size_mismatch_retries_144_before_ocr(self):
        p,_=self.fixture();page=self.open(p)
        expected=page.to_image(resolution=144).original
        first=Image.new('RGB',(100,100),'white')
        with patch.object(page,'to_image',side_effect=[SimpleNamespace(original=first),SimpleNamespace(original=expected)]) as render,patch('convert._ocr',return_value=([],None)) as ocr:
            self.assertEqual(scan_tables(page),[])
        self.assertEqual(render.call_count,2)
        self.assertGreater(render.call_args_list[0].kwargs['resolution'],144)
        self.assertEqual(render.call_args_list[1].kwargs['resolution'],144)
        self.assertEqual(ocr.call_count,1)
        self.assertEqual(ocr.call_args.args[0].shape[:2],(expected.height,expected.width))

    def test_actual_render_budget_checked_before_ocr(self):
        p,_=self.fixture();page=self.open(p)
        oversized=SimpleNamespace(width=5000,height=4001,size=(5000,4001))
        oversized.convert=lambda mode:oversized
        with patch('scan_raster.resolution',return_value=144),patch.object(page,'to_image',return_value=SimpleNamespace(original=oversized)),patch('convert._ocr',side_effect=AssertionError('Oversize render reached OCR')):
            with self.assertRaises(ConversionError):scan_tables(page)

    def test_legacy_144_and_physical_dimensions(self):
        p,_=self.fixture();page=self.open(p)
        with patch('convert._ocr',return_value=([],None)),patch('scan_raster.resolution',return_value=144):
            self.assertEqual(scan_tables(page),[])

if __name__=='__main__':unittest.main()
