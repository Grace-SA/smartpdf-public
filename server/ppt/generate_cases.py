"""Generate original public synthetic PPTX cases; test-only python-pptx dependency."""
import hashlib
import json
import sys
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image, ImageDraw


def generate(root):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    png = root / 'synthetic.png'
    image = Image.new('RGBA', (240, 120), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image); draw.rectangle((20, 20, 220, 100), fill=(30, 150, 100, 255)); image.save(png)
    jpeg = root / 'synthetic.jpg'; image.convert('RGB').save(jpeg)
    cases = ['wide', 'four-three', 'custom', 'portrait', 'chinese', 'wrapping', 'table', 'merged-table',
             'column-chart', 'bar-chart', 'line-chart', 'area-chart', 'pie-chart', 'doughnut-chart', 'scatter-chart',
             'png', 'jpeg', 'transparency', 'rotated-shapes', 'theme-master', 'hidden', 'notes', 'hyperlink', 'blank']
    result = []
    for index, kind in enumerate(cases, 1):
        p = Presentation(); p.slide_width = Inches(13.333333); p.slide_height = Inches(7.5)
        if kind == 'four-three': p.slide_width = Inches(10)
        if kind == 'custom': p.slide_width, p.slide_height = Inches(11), Inches(5)
        if kind == 'portrait': p.slide_width, p.slide_height = Inches(7.5), Inches(10)
        slide = p.slides.add_slide(p.slide_layouts[6])
        marker = f'PPT_CASE_{index:02d}'
        box = slide.shapes.add_textbox(Inches(.5), Inches(.3), Inches(6), Inches(.8))
        box.text = marker; box.text_frame.paragraphs[0].font.size = Pt(24)
        expected = [marker]
        if kind == 'chinese':
            box.text += '\n中文演示文稿'; expected.append('中文演示文稿')
        elif kind == 'wrapping':
            box = slide.shapes.add_textbox(Inches(.5), Inches(1.5), Inches(4), Inches(4))
            box.text_frame.word_wrap = True
            box.text = 'SYNTHETIC_WRAPPING ' + 'Readable slide content. ' * 12
            expected.append('SYNTHETIC_WRAPPING')
        elif kind in ('table', 'merged-table'):
            table = slide.shapes.add_table(4, 3, Inches(.5), Inches(1.5), Inches(6), Inches(3)).table
            for r in range(4):
                for c in range(3): table.cell(r, c).text = f'R{r}C{c}'
            if kind == 'merged-table': table.cell(0,0).merge(table.cell(0,1))
            expected.append('R3C2')
        elif kind.endswith('-chart'):
            chart_type = {'column-chart': XL_CHART_TYPE.COLUMN_CLUSTERED, 'bar-chart': XL_CHART_TYPE.BAR_CLUSTERED,
                          'line-chart': XL_CHART_TYPE.LINE, 'area-chart': XL_CHART_TYPE.AREA,
                          'pie-chart': XL_CHART_TYPE.PIE, 'doughnut-chart': XL_CHART_TYPE.DOUGHNUT,
                          'scatter-chart': XL_CHART_TYPE.XY_SCATTER}[kind]
            if kind == 'scatter-chart':
                data = XyChartData(); series=data.add_series('SyntheticSeries'); series.add_data_point(1,3); series.add_data_point(2,7)
            else:
                data = CategoryChartData(); data.categories=['Alpha','Beta','Gamma']; data.add_series('SyntheticSeries',(3,7,5))
            slide.shapes.add_chart(chart_type, Inches(.5), Inches(1.5), Inches(7), Inches(4), data)
        elif kind in ('png', 'jpeg', 'transparency'):
            pic = slide.shapes.add_picture(str(jpeg if kind == 'jpeg' else png), Inches(.8), Inches(1.5), width=Inches(5))
            if kind == 'png': pic.crop_left = .1
        elif kind == 'rotated-shapes':
            shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(2), Inches(4), Inches(2))
            shape.rotation = 15; shape.fill.solid(); shape.fill.fore_color.rgb=RGBColor(30,150,100)
            shape.text='ROTATED_SHAPE'; expected.append('ROTATED_SHAPE')
        elif kind == 'theme-master':
            slide = p.slides.add_slide(p.slide_layouts[0]); slide.shapes.title.text='MASTER_TITLE'; expected.append('MASTER_TITLE')
        elif kind == 'hidden':
            hidden = p.slides.add_slide(p.slide_layouts[6]); hidden._element.set('show','0')
            hidden.shapes.add_textbox(Inches(1),Inches(1),Inches(5),Inches(2)).text='SYNTHETIC_HIDDEN_SECRET'
            slide=p.slides.add_slide(p.slide_layouts[6]); slide.shapes.add_textbox(Inches(1),Inches(1),Inches(5),Inches(2)).text='VISIBLE_AFTER_HIDDEN'
            expected.append('VISIBLE_AFTER_HIDDEN')
        elif kind == 'notes':
            slide.notes_slide.notes_text_frame.text='SYNTHETIC_SPEAKER_NOTES_SECRET'
        elif kind == 'hyperlink':
            run=box.text_frame.paragraphs[0].runs[0]; run.hyperlink.address='https://example.invalid/synthetic'
        elif kind == 'blank':
            p.slides.add_slide(p.slide_layouts[6])
        destination = root / f'{index:02d}-{kind}'; destination.mkdir(exist_ok=True)
        source = destination/'input.pptx'; p.save(source)
        result.append({'id': index, 'kind':kind, 'directory':destination.name,
                       'sha256':hashlib.sha256(source.read_bytes()).hexdigest(), 'text':expected,
                       'visible': len(p.slides)-(1 if kind=='hidden' else 0),
                       'width':p.slide_width/12700,'height':p.slide_height/12700})
    (root/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__': generate(sys.argv[1])
