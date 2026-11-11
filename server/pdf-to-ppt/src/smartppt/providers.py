"""Adobe REST adapter. No automatic paid-job resubmission on ambiguous timeout."""
import time
from urllib.parse import urlsplit
import httpx
from .config import ConversionError

API = 'https://pdf-services.adobe.io'
STORAGE_HOSTS = {
    'dcplatformstorageservice-prod-us-east-1.s3-accelerate.amazonaws.com',
    'dcplatformstorageservice-prod-eu-west-1.s3.amazonaws.com',
}
API_HOSTS = {'pdf-services.adobe.io', 'pdf-services-ue1.adobe.io', 'pdf-services-ew1.adobe.io'}
LANGUAGES = {'en-US', 'zh-CN', 'zh-TW', 'ja-JP', 'ko-KR', 'de-DE', 'fr-FR', 'es-ES'}


def trusted_url(url, storage=False):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in (STORAGE_HOSTS if storage else API_HOSTS)
            or p.port not in (None, 443) or p.username or p.password):
        raise ConversionError('untrusted_provider_url')
    return url


class AdobeProvider:
    def __init__(self, settings, client=None, sleep=time.sleep, clock=time.monotonic):
        self.settings = settings
        # The provider and storage origins are explicit operator configuration.
        # Ambient proxy settings must not redirect document/credential traffic.
        self.client = client or httpx.Client(timeout=45, follow_redirects=False, trust_env=False)
        self.sleep, self.clock = sleep, clock

    def request(self, method, url, **kwargs):
        for attempt in range(3):
            try:
                response = self.client.request(method, url, **kwargs)
            except httpx.HTTPError as e:
                raise ConversionError('provider_network_error') from e
            # Retry only reads. Repeating export POST can double-charge.
            if method == 'GET' and response.status_code in (429, 502, 503, 504) and attempt < 2:
                raw = response.headers.get('Retry-After', str(2**attempt))
                delay = min(10, max(0, float(raw))) if raw.replace('.', '', 1).isdigit() else 2**attempt
                self.sleep(delay)
                continue
            if response.status_code >= 400:
                code = {401:'provider_auth', 403:'provider_auth', 429:'provider_rate_limit'}.get(response.status_code, 'provider_error')
                raise ConversionError(code)
            if 300 <= response.status_code < 400:
                raise ConversionError('provider_redirect_rejected')
            return response

    def convert(self, source, target, language='en-US', submitted=lambda _: None, cancelled=lambda:False):
        if not self.settings.editable_available:
            raise ConversionError('provider_not_configured')
        if language not in LANGUAGES:
            raise ConversionError('unsupported_language')
        deadline = self.clock() + self.settings.job_timeout
        try:
            token = self.request('POST', API+'/token', data={
                'client_id': self.settings.adobe_id, 'client_secret': self.settings.adobe_secret}).json()['access_token']
            headers = {'Authorization':'Bearer '+token, 'x-api-key':self.settings.adobe_id}
            asset = self.request('POST', API+'/assets', headers=headers, json={'mediaType':'application/pdf'}).json()
            upload = trusted_url(asset['uploadUri'], storage=True)
            with source.open('rb') as stream:
                self.request('PUT', upload, content=stream, headers={'Content-Type':'application/pdf'})
            if cancelled():
                raise ConversionError('cancelled')
            response = self.request('POST', API+'/operation/exportpdf', headers=headers,
                                    json={'assetID':asset['assetID'], 'targetFormat':'pptx', 'ocrLang':language})
            status_url = trusted_url(response.headers['location'])
            submitted(status_url)
            while self.clock() < deadline:
                if cancelled():
                    raise ConversionError('cancelled')
                result = self.request('GET', status_url, headers=headers).json()
                if result['status'] == 'failed':
                    raise ConversionError('provider_conversion_failed')
                if result['status'] == 'done':
                    url = trusted_url(result['asset']['downloadUri'], storage=True)
                    # Signed URLs receive no API credentials; never follow redirects.
                    with self.client.stream('GET', url) as stream:
                        if stream.status_code != 200:
                            raise ConversionError('provider_download_failed')
                        total = 0
                        with target.open('wb') as out:
                            for chunk in stream.iter_bytes():
                                total += len(chunk)
                                if total > 100*1024*1024:
                                    raise ConversionError('output_size_limit')
                                out.write(chunk)
                    return
                if result['status'] not in ('in progress', 'pending'):
                    raise ConversionError('provider_protocol_error')
                self.sleep(2)
            raise ConversionError('provider_timeout')
        except ConversionError:
            raise
        except (KeyError, ValueError, TypeError, httpx.HTTPError) as e:
            raise ConversionError('provider_protocol_error') from e
