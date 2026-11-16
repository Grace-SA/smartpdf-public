from pathlib import Path
import httpx
import pytest
from smartppt.config import ConversionError
from smartppt.stirling import StirlingProvider


def test_stirling_is_only_available_provider(monkeypatch, tmp_path):
    from smartppt.config import Settings
    monkeypatch.delenv('SMARTPPT_EDITABLE_PROVIDER', raising=False)
    monkeypatch.setenv('SMARTPPT_STIRLING_URL', 'http://127.0.0.1:8766')
    settings = Settings(root=tmp_path)
    assert settings.editable_provider == 'stirling' and settings.editable_available
    settings.editable_provider = 'adobe'
    assert not settings.editable_available
    assert not hasattr(settings, 'adobe_id') and not hasattr(settings, 'adobe_secret')


def test_capabilities_never_advertise_cloud_ocr(settings):
    from fastapi.testclient import TestClient
    from smartppt.api import create_app
    settings.stirling_url = 'http://127.0.0.1:8766'
    with TestClient(create_app(settings)) as client:
        data = client.get('/api/capabilities').json()
    assert data['editable_provider'] == 'stirling'
    assert data['cloud_provider'] is None
    assert data['ocr_language_selection'] is False
    assert data['ocr_available'] is False


def configured(settings):
    settings.editable_provider='stirling'
    settings.stirling_url='http://127.0.0.1:8766'
    return settings


def test_real_contract(settings,pdf_file,tmp_path):
    settings=configured(settings);settings.stirling_key='test-only'
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.path=='/api/v1/convert/pdf/presentation'
        assert request.url.params['useStirlingOfficeConvert']=='true'
        assert request.headers['X-API-KEY']=='test-only'
        body=request.read()
        assert b'name="fileInput"' in body and b'name="outputFormat"' in body and b'pptx' in body
        return httpx.Response(200,content=b'output-checked-by-worker')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        target=tmp_path/'output'
        StirlingProvider(settings,client).convert(pdf_file,target)
        assert target.read_bytes()==b'output-checked-by-worker'
    assert len(calls)==1 and settings.editable_available


@pytest.mark.parametrize('origin',['','file:///tmp','http://remote.test','http://u:p@localhost',
    'https://host/path','https://host?x=1','https://host/#x','https://host:bad'])
def test_reject_invalid_origin(settings,origin):
    settings.stirling_url=origin
    with pytest.raises(ConversionError,match='invalid_stirling_url'):StirlingProvider(settings)


@pytest.mark.parametrize('status,code',[(302,'provider_error'),(401,'provider_auth'),
    (403,'provider_unavailable'),(429,'provider_rate_limit'),(500,'provider_error')])
def test_failure_no_retry(settings,pdf_file,tmp_path,status,code):
    calls=[]
    def handler(request):
        calls.append(request);return httpx.Response(status,headers={'Location':'https://other.test'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConversionError,match=code):
            StirlingProvider(configured(settings),client).convert(pdf_file,tmp_path/'out')
    assert len(calls)==1 and not (tmp_path/'out').exists()


@pytest.mark.parametrize('payload,limit,code',[(b'',20,'invalid_pptx'),(b'12345',4,'output_size_limit')])
def test_bad_body_cleanup(settings,pdf_file,tmp_path,payload,limit,code):
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=payload))) as client:
        provider=StirlingProvider(configured(settings),client);provider.max_output_bytes=limit
        with pytest.raises(ConversionError,match=code):provider.convert(pdf_file,tmp_path/'out')
        assert not (tmp_path/'out').exists()


def test_timeout_no_retry(settings,pdf_file,tmp_path):
    calls=[]
    def handler(request):
        calls.append(request);raise httpx.ReadTimeout('timed out')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConversionError,match='provider_timeout'):
            StirlingProvider(configured(settings),client).convert(pdf_file,tmp_path/'out')
    assert len(calls)==1


def test_cancel_before_submit(settings,pdf_file,tmp_path):
    def handler(request):raise AssertionError('must not submit')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConversionError,match='cancelled'):
            StirlingProvider(configured(settings),client).convert(pdf_file,tmp_path/'out',cancelled=lambda:True)
