import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import pytest
from pypdf import PdfReader, PdfWriter
from pptx import Presentation
from pptx.util import Inches
from smartppt.config import ConversionError
from smartppt.pdf import inspect_pdf, render_page
from smartppt.preserve import convert_preserve
from smartppt.quality import inspect_pptx, text_metrics
from smartppt.store import Store
from smartppt.worker import run_job, work_once


def test_preflight_and_render(pdf_file):
    info=inspect_pdf(pdf_file)
    assert info['page_count']==2 and not info['mixed_sizes']
    assert '$12,345.67' in info['pages'][0]['text']
    assert render_page(pdf_file,0).size==(1440,810)

@pytest.mark.parametrize('content',[b'',b'not pdf',b'%PDF-1.7\nbroken'])
def test_invalid_input(tmp_path,content):
    p=tmp_path/'bad.pdf';p.write_bytes(content)
    with pytest.raises(ConversionError):inspect_pdf(p)

def test_encrypted(pdf_file,tmp_path):
    writer=PdfWriter(clone_from=pdf_file);writer.encrypt('secret')
    out=tmp_path/'encrypted.pdf';writer.write(out)
    with pytest.raises(ConversionError,match='encrypted_pdf'):inspect_pdf(out)

def test_limits(pdf_file):
    with pytest.raises(ConversionError,match='file_size_limit'):inspect_pdf(pdf_file,max_bytes=20)
    with pytest.raises(ConversionError,match='page_limit'):inspect_pdf(pdf_file,max_pages=1)

def test_unsupported_encryption_is_not_called_corrupt(pdf_file,monkeypatch):
    from pypdf.errors import DependencyError
    def unavailable(*args,**kwargs):raise DependencyError('cryptography required')
    monkeypatch.setattr('smartppt.pdf.PdfReader',unavailable)
    with pytest.raises(ConversionError,match='encryption_unsupported'):inspect_pdf(pdf_file)

def test_mixed_rotation(pdf_file,tmp_path):
    writer=PdfWriter(clone_from=pdf_file);writer.pages[1].rotate(90)
    out=tmp_path/'rotation.pdf';writer.write(out)
    info=inspect_pdf(out)
    assert info['mixed_sizes']
    assert info['pages'][1]['width']==405

def test_preserve_is_not_editable(pdf_file,tmp_path):
    info=inspect_pdf(pdf_file);out=tmp_path/'out.pptx'
    convert_preserve(pdf_file,out,info)
    report=inspect_pptx(out,info,'preserve')
    assert report['verdict']=='appearance_only'
    assert all(x['editable_characters']==0 for x in report['pages'])
    editable_report=inspect_pptx(out,info,'editable')
    assert editable_report['verdict']=='needs_review'
    assert sum(x['code']=='text_mismatch' for x in editable_report['warnings'])==2

def test_tiny_pdf_canvas(tmp_path):
    source=tmp_path/'tiny.pdf';writer=PdfWriter();writer.add_blank_page(width=40,height=50);writer.write(source)
    out=tmp_path/'tiny.pptx';info=inspect_pdf(source);convert_preserve(source,out,info)
    prs=Presentation(out)
    assert prs.slide_width>=914400 and prs.slide_height>=914400
    assert inspect_pptx(out,info,'preserve')['slide_count']==1

def test_pptx_count_gate(pdf_file,tmp_path):
    out=tmp_path/'wrong.pptx';prs=Presentation();prs.save(out)
    with pytest.raises(ConversionError,match='page_count_mismatch'):inspect_pptx(out,inspect_pdf(pdf_file),'editable')

def test_text_metrics_do_not_confuse_precision_recall():
    assert text_metrics('ABC','ABC')['character_recall']==1
    assert text_metrics('ABC','ABCXXX')['character_precision']==.5
    assert text_metrics('ABC','AC')['character_recall']==pytest.approx(2/3)
    assert text_metrics('中文123.45','中文123.54')['sequence_similarity']<1
    assert text_metrics('','OCR')['character_recall'] is None

@pytest.mark.parametrize('member',['../escape','/absolute','ppt/vbaProject.bin'])
def test_unsafe_zip(tmp_path,member):
    out=tmp_path/'bad.pptx'
    with zipfile.ZipFile(out,'w') as z:z.writestr(member,'x')
    with pytest.raises(ConversionError,match='unsafe_output'):inspect_pptx(out,{'page_count':0},'editable')

def test_external_image_rejected(tmp_path):
    out=tmp_path/'bad.pptx'
    with zipfile.ZipFile(out,'w') as z:z.writestr('_rels/.rels','<Relationships><Relationship TargetMode="External" Type="test/image" Target="http://127.0.0.1/secret"/></Relationships>')
    with pytest.raises(ConversionError,match='external_output_resource'):inspect_pptx(out,{},'editable')

def test_store_tokens_and_atomic_claim(settings):
    store=Store(settings);job,token=store.create('preserve','en-US')
    assert store.get(job,token) and not store.get(job,'wrong')
    store.update(job,'queued',('uploading',))
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims=list(pool.map(lambda _:Store(settings).claim(),range(8)))
    assert claims.count(job)==1

def test_queue_limit(settings):
    settings.max_queue=1;store=Store(settings);store.create('preserve','en-US')
    with pytest.raises(ConversionError,match='queue_full'):store.create('preserve','en-US')

def test_cancel_cannot_be_overwritten(settings):
    store=Store(settings);job,_=store.create('preserve','en-US')
    store.update(job,'cancelled',('uploading',))
    assert not store.update(job,'ready',('validating',))
    assert store.get(job)['state']=='cancelled'
    store.cleanup();assert not (settings.root/job).exists()

def test_expiry_and_stale_job(settings):
    store=Store(settings);job,_=store.create('preserve','en-US')
    with store.connect() as c:c.execute('UPDATE jobs SET expires=0 WHERE id=?',(job,))
    store.cleanup();assert store.get(job)['state']=='expired'
    job,_=store.create('editable','en-US')
    with store.connect() as c:c.execute("UPDATE jobs SET state='processing',updated=0 WHERE id=?",(job,))
    store.cleanup();assert store.get(job)['error']=='worker_interrupted'

def test_real_worker_smoke(settings,pdf_file):
    store=Store(settings);job,_=store.create('preserve','en-US')
    (settings.root/job/'input.pdf').write_bytes(pdf_file.read_bytes())
    store.update(job,'queued',('uploading',))
    assert work_once(settings)
    assert store.get(job)['state']=='ready'
    assert (settings.root/job/'output.pptx').is_file()
    assert not work_once(settings)

def test_worker_fails_closed_without_cloud(settings,pdf_file):
    settings.stirling_url=''
    store=Store(settings);job,_=store.create('editable','en-US')
    (settings.root/job/'input.pdf').write_bytes(pdf_file.read_bytes())
    store.update(job,'processing',('uploading',));run_job(settings,job)
    assert store.get(job)['error']=='provider_not_configured'
    assert not (settings.root/job/'output.pptx').exists()
