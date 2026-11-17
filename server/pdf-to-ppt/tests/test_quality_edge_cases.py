import pytest
from pptx import Presentation
from pptx.util import Inches
from smartppt.quality import inspect_pptx, numeric_tokens
from smartppt.config import ConversionError
import httpx


def test_transposed_numeric_digits_flagged(tmp_path):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_textbox(0,0,Inches(4),Inches(1)).text='Total 123.54'
    out=tmp_path/'numbers.pptx';prs.save(out)
    info={'page_count':1,'mixed_sizes':False,'pages':[{'number':1,'text':'Total 123.45','needs_ocr_check':False}]}
    report=inspect_pptx(out,info,'editable')
    assert any(x['code']=='numeric_mismatch' for x in report['warnings'])
    assert report['pages'][0]['character_recall']==1  # A histogram alone misses this.

def test_native_table_text_and_scan_review(tmp_path):
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6])
    table=slide.shapes.add_table(1,2,0,0,Inches(4),Inches(1)).table
    table.cell(0,0).text='中文';table.cell(0,1).text='42'
    out=tmp_path/'table.pptx';prs.save(out)
    info={'page_count':1,'mixed_sizes':False,'pages':[{'number':1,'text':'中文 42','needs_ocr_check':True}]}
    report=inspect_pptx(out,info,'editable')
    assert report['pages'][0]['character_recall']==1
    assert {'page':1,'code':'ocr_needs_ground_truth'} in report['warnings']

def test_worker_cancellation_during_conversion(settings,pdf_file,monkeypatch):
    from smartppt.store import Store
    from smartppt.worker import run_job
    from smartppt.preserve import convert_preserve
    store=Store(settings);job,_=store.create('preserve','en-US')
    (settings.root/job/'input.pdf').write_bytes(pdf_file.read_bytes())
    store.update(job,'processing',('uploading',))
    def cancel_after(source,target,info):
        convert_preserve(source,target,info)
        store.update(job,'cancelled',('processing',))
    monkeypatch.setattr('smartppt.preserve.convert_preserve',cancel_after)
    run_job(settings,job)
    assert store.get(job)['state']=='cancelled'
    assert not (settings.root/job/'output.pptx').exists()
