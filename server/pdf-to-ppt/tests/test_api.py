from fastapi.testclient import TestClient
import pytest
from smartppt.api import create_app
from smartppt.worker import run_job


def upload(client,pdf_file,mode='preserve'):
    return client.post('/api/jobs?mode='+mode,content=pdf_file.read_bytes(),headers={'Content-Type':'application/pdf'})

def test_api_end_to_end(settings,pdf_file):
    app=create_app(settings)
    with TestClient(app) as client:
        result=upload(client,pdf_file);assert result.status_code==202,result.text
        data=result.json();job=data['id'];headers={'Authorization':'Bearer '+data['token']}
        assert data['page_count']==2
        assert client.get('/api/jobs/'+job).status_code==404
        assert client.get('/api/jobs/'+job,headers={'Authorization':'Bearer bad'}).status_code==404
        assert client.get('/api/jobs/'+job+'/download',headers=headers).status_code==409
        app.state.store.update(job,'processing',('queued',));run_job(settings,job)
        assert client.get('/api/jobs/'+job,headers=headers).json()['state']=='ready'
        response=client.get('/api/jobs/'+job+'/download',headers=headers)
        assert response.status_code==200 and response.content.startswith(b'PK')
        assert 'no-store' in response.headers['cache-control']
        assert client.delete('/api/jobs/'+job,headers=headers).status_code==200
        assert client.get('/api/jobs/'+job+'/download',headers=headers).status_code==409
        assert not (settings.root/job).exists()

def test_api_missing_provider(settings,pdf_file):
    settings.stirling_url=''
    with TestClient(create_app(settings)) as client:
        assert not client.get('/api/capabilities').json()['editable_available']
        assert upload(client,pdf_file,'editable').status_code==503

@pytest.mark.parametrize('query,status',[('mode=bogus',422),('mode=preserve&language=xx',422)])
def test_invalid_options(settings,query,status):
    with TestClient(create_app(settings)) as client:
        assert client.post('/api/jobs?'+query).status_code==status

def test_input_limits(settings,pdf_file):
    settings.max_bytes=100
    with TestClient(create_app(settings)) as client:
        assert upload(client,pdf_file).status_code==413
        assert client.post('/api/jobs?mode=preserve',content='bad').status_code==415

def test_malformed_pdf_cleanup(settings):
    with TestClient(create_app(settings)) as client:
        r=client.post('/api/jobs?mode=preserve',content=b'%PDF-broken',headers={'Content-Type':'application/pdf'})
        assert r.status_code==422
        assert not list(settings.root.glob('*/input.pdf'))

def test_expired_job(settings,pdf_file):
    app=create_app(settings)
    with TestClient(app) as client:
        data=upload(client,pdf_file).json()
        with app.state.store.connect() as c:c.execute('UPDATE jobs SET expires=0 WHERE id=?',(data['id'],))
        assert client.get('/api/jobs/'+data['id'],headers={'Authorization':'Bearer '+data['token']}).status_code==410
