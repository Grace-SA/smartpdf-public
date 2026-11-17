import hashlib,os
from pathlib import Path
from io import BytesIO
import pytest,numpy as np
from PIL import Image,ImageDraw,ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from pptx import Presentation
from pptx.util import Pt
import pypdfium2 as pdfium
from smartppt.assisted import ocr_slide


def sample_font(language):
 if language=='en':return ImageFont.load_default(size=32)
 path=os.getenv('SMARTPPT_CJK_FONT')
 if not path or not Path(path).is_file():pytest.skip('CJK font required')
 font=ImageFont.truetype(path,32)
 try:font.set_variation_by_axes([400])
 except OSError:pass
 return font

@pytest.mark.parametrize('language',['en','zh'])
@pytest.mark.parametrize('background,foreground',[((16,48,110),(255,255,255)),((24,24,24),(240,240,240)),((16,48,110),(255,235,40)),((255,255,255),(20,20,20))])
def test_uniform_background_preserves_text_color_and_pixels_outside_verified_erase(tmp_path,language,background,foreground):
 text='Revenue 1234.56' if language=='en' else '含税收入1234.56元'
 font=sample_font(language)
 image=Image.new('RGB',(700,180),background);draw=ImageDraw.Draw(image);box=draw.textbbox((30,40),text,font=font);draw.text((30,40),text,font=font,fill=foreground)
 path=tmp_path/'scan.png';image.save(path);source=tmp_path/'scan.pdf';c=canvas.Canvas(str(source),pagesize=(350,90));c.drawImage(ImageReader(image),0,0,350,90);c.save()
 l,t,r,b=box;polygon=[[l-4,t-4],[r+4,t-4],[r+4,b+4],[l-4,b+4]]
 record={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'image_size':[700,180],'lines':[{'text':text,'confidence':1.0,'polygon':polygon}]}
 prs=Presentation();prs.slide_width=Pt(350);prs.slide_height=Pt(90);slide=prs.slides.add_slide(prs.slide_layouts[6])
 with pdfium.PdfDocument(source) as d:report=ocr_slide(prs,slide,d[0],path,record,line_approvals=[True])
 assert report['editable_lines']==1,report
 assert slide.shapes[1].text==text
 assert tuple(slide.shapes[1].text_frame.paragraphs[0].runs[0].font.color.rgb)==foreground
 with Image.open(BytesIO(slide.shapes[0].image.blob)) as clean:actual=np.asarray(clean)
 expected=np.asarray(image);assert np.array_equal(actual[:t-5],expected[:t-5]);assert np.array_equal(actual[b+5:],expected[b+5:]);assert np.all(actual[t:b,l:r]==background)


def test_nonuniform_background_is_not_erased(tmp_path):
 image=Image.new('RGB',(500,200),'#10306e');draw=ImageDraw.Draw(image)
 for x in range(500):draw.line((x,0,x,199),fill=(x//2,48,110))
 font=sample_font('en');draw.text((30,50),'Revenue 123',font=font,fill='white');p=tmp_path/'scan.png';image.save(p)
 source=tmp_path/'scan.pdf';c=canvas.Canvas(str(source),pagesize=(250,100));c.drawImage(ImageReader(image),0,0,250,100);c.save()
 record={'input_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'image_size':[500,200],'lines':[{'text':'Revenue 123','confidence':1.,'polygon':[[20,40],[260,40],[260,100],[20,100]]}]}
 prs=Presentation();prs.slide_width=Pt(250);prs.slide_height=Pt(100);slide=prs.slides.add_slide(prs.slide_layouts[6])
 with pdfium.PdfDocument(source) as d:report=ocr_slide(prs,slide,d[0],p,record,line_approvals=[True])
 assert report['editable_lines']==0 and 'nonuniform_background_kept_as_image' in report['warnings']
 with Image.open(BytesIO(slide.shapes[0].image.blob)) as clean:assert np.array_equal(np.asarray(clean),np.asarray(image))


def test_multiple_text_colors_are_not_flattened_into_one_color(tmp_path):
 image=Image.new('RGB',(700,180),(16,48,110));draw=ImageDraw.Draw(image);font=sample_font('en')
 first='Revenue ';second='1234.56';text=first+second
 draw.text((30,40),first,font=font,fill='white');draw.text((30+font.getlength(first),40),second,font=font,fill=(255,235,40))
 l,t,r,b=draw.textbbox((30,40),text,font=font);path=tmp_path/'scan.png';image.save(path)
 source=tmp_path/'scan.pdf';c=canvas.Canvas(str(source),pagesize=(350,90));c.drawImage(ImageReader(image),0,0,350,90);c.save()
 record={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'image_size':[700,180],'lines':[{'text':text,'confidence':1.,'polygon':[[l-4,t-4],[r+4,t-4],[r+4,b+4],[l-4,b+4]]}]}
 prs=Presentation();prs.slide_width=Pt(350);prs.slide_height=Pt(90);slide=prs.slides.add_slide(prs.slide_layouts[6])
 with pdfium.PdfDocument(source) as d:report=ocr_slide(prs,slide,d[0],path,record,line_approvals=[True])
 assert report['editable_lines']==0,'A single-color run must not replace differently colored source text'
 with Image.open(BytesIO(slide.shapes[0].image.blob)) as clean:assert np.array_equal(np.asarray(clean),np.asarray(image))
