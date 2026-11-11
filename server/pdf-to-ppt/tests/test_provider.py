import json
import httpx
import pytest
from smartppt.providers import AdobeProvider, trusted_url, API
from smartppt.config import ConversionError

STORAGE='https://dcplatformstorageservice-prod-us-east-1.s3-accelerate.amazonaws.com/'

@pytest.mark.parametrize('url',['http://pdf-services.adobe.io/a','https://127.0.0.1/a','https://pdf-services.adobe.io.evil.test/a','https://user:pass@pdf-services.adobe.io/a','https://pdf-services.adobe.io:999/a'])
def test_ssrf_rejected(url):
    with pytest.raises(ConversionError):trusted_url(url)

def test_contract_success_and_credential_isolation(settings,pdf_file,tmp_path):
    settings.adobe_id='id';settings.adobe_secret='secret';seen=[]
    def respond(request):
        seen.append(request)
        path=request.url.path
        if path=='/token':return httpx.Response(200,json={'access_token':'token'})
        if path=='/assets':return httpx.Response(200,json={'assetID':'asset','uploadUri':STORAGE+'upload'})
        if path=='/upload':
            assert 'authorization' not in request.headers
            assert request.content.startswith(b'%PDF-');return httpx.Response(200)
        if path=='/operation/exportpdf':
            assert json.loads(request.content)=={'assetID':'asset','targetFormat':'pptx','ocrLang':'zh-CN'}
            return httpx.Response(201,headers={'location':API+'/status'})
        if path=='/status':return httpx.Response(200,json={'status':'done','asset':{'downloadUri':STORAGE+'download'}})
        assert path=='/download' and 'authorization' not in request.headers
        return httpx.Response(200,content=b'PK-mock-pptx')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        saved=[];target=tmp_path/'result'
        AdobeProvider(settings,client).convert(pdf_file,target,'zh-CN',submitted=saved.append)
        assert target.read_bytes()==b'PK-mock-pptx' and saved==[API+'/status']
        assert len(seen)==6

@pytest.mark.parametrize('status,code',[(401,'provider_auth'),(403,'provider_auth'),(429,'provider_rate_limit'),(500,'provider_error'),(302,'provider_redirect_rejected')])
def test_no_post_retry(settings,status,code):
    seen=[]
    with httpx.Client(transport=httpx.MockTransport(lambda r:(seen.append(r),httpx.Response(status))[1])) as client:
        with pytest.raises(ConversionError,match=code):AdobeProvider(settings,client).request('POST',API+'/operation/exportpdf')
    assert len(seen)==1

def test_get_retry(settings):
    seen=[];sleeps=[]
    def handler(r):
        seen.append(r)
        return httpx.Response(503 if len(seen)<3 else 200,headers={'Retry-After':'1000'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert AdobeProvider(settings,client,sleep=sleeps.append).request('GET',API+'/status').status_code==200
    assert sleeps==[10,10]

def test_network_error_sanitized(settings):
    def handler(r):raise httpx.ConnectError('secret-bearing-url',request=r)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConversionError,match='provider_network_error') as caught:
            AdobeProvider(settings,client).request('POST',API+'/token')
        assert 'secret' not in str(caught.value)
