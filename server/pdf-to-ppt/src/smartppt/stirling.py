"""Opt-in self-hosted Stirling adapter. No cloud fallback or automatic retry."""
import ipaddress
from urllib.parse import urlsplit
import httpx
from .config import ConversionError


class StirlingProvider:
    max_output_bytes = 100 * 1024 * 1024

    def __init__(self, settings, client=None):
        self.settings = settings
        try:
            url = urlsplit(settings.stirling_url)
            loopback = url.hostname == 'localhost'
            if url.hostname:
                try:
                    loopback = loopback or ipaddress.ip_address(url.hostname).is_loopback
                except ValueError:
                    pass
            if (not url.hostname or url.username or url.password or url.query or url.fragment
                    or url.path not in ('', '/') or url.scheme not in ('http', 'https')
                    or (url.scheme == 'http' and not loopback)):
                raise ValueError('invalid origin')
            url.port
        except ValueError as error:
            raise ConversionError('invalid_stirling_url') from error
        # The origin is operator configuration, never upload/request data.
        self.endpoint = settings.stirling_url.rstrip('/') + '/api/v1/convert/pdf/presentation'
        self.client = client or httpx.Client(timeout=settings.job_timeout, trust_env=False, follow_redirects=False)

    def convert(self, source, target, language='en-US', submitted=lambda _: None, cancelled=lambda:False):
        if cancelled():
            raise ConversionError('cancelled')
        headers = {'X-API-KEY': self.settings.stirling_key} if self.settings.stirling_key else {}
        try:
            with source.open('rb') as input_file, self.client.stream('POST', self.endpoint,
                    params={'useStirlingOfficeConvert': 'true'},
                    headers=headers, data={'outputFormat': 'pptx'},
                    files={'fileInput': ('input.pdf', input_file, 'application/pdf')}) as response:
                if response.status_code != 200:
                    codes = {401:'provider_auth',403:'provider_unavailable',429:'provider_rate_limit'}
                    raise ConversionError(codes.get(response.status_code, 'provider_error'))
                # language is intentionally unused: this endpoint does not perform OCR.
                total = 0
                with target.open('wb') as output:
                    for chunk in response.iter_bytes():
                        if cancelled():
                            raise ConversionError('cancelled')
                        total += len(chunk)
                        if total > self.max_output_bytes:
                            raise ConversionError('output_size_limit')
                        output.write(chunk)
                if not total:
                    raise ConversionError('invalid_pptx')
        except httpx.TimeoutException as error:
            target.unlink(missing_ok=True)
            raise ConversionError('provider_timeout') from error
        except httpx.HTTPError as error:
            target.unlink(missing_ok=True)
            raise ConversionError('provider_network_error') from error
        except Exception:
            target.unlink(missing_ok=True)
            raise
