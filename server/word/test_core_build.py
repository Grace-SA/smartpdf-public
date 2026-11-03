import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from core_build import download, extract_fonts


class CoreInputs(unittest.TestCase):
    def test_rejects_http_without_network_access(self):
        with tempfile.TemporaryDirectory() as folder, patch('core_build.urllib.request.urlopen') as open_url:
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                download({'url':'http://example.invalid/input','sha256':'0'*64}, Path(folder)/'input')
            open_url.assert_not_called()

    def test_checksum_failure_never_promotes_download(self):
        with tempfile.TemporaryDirectory() as folder, patch('core_build.urllib.request.urlopen', return_value=io.BytesIO(b'synthetic')):
            target=Path(folder)/'input'
            with self.assertRaisesRegex(ValueError, 'checksum'):
                download({'url':'https://example.invalid/input','sha256':'0'*64}, target)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.part').exists())

    def test_verified_download_is_promoted(self):
        with tempfile.TemporaryDirectory() as folder, patch('core_build.urllib.request.urlopen', return_value=io.BytesIO(b'synthetic')):
            target=Path(folder)/'input'
            download({'url':'https://example.invalid/input','sha256':hashlib.sha256(b'synthetic').hexdigest()}, target)
            self.assertEqual(target.read_bytes(),b'synthetic')

    def test_restricted_archive_is_refused_before_font_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            jar=Path(folder)/'input.jar'
            with zipfile.ZipFile(jar,'w') as archive: archive.writestr('BOOT-INF/lib/proprietary-1.jar',b'synthetic')
            with self.assertRaisesRegex(ValueError, 'excluded'):
                extract_fonts(jar,Path(folder)/'fonts',{'fonts':[]})
            self.assertFalse((Path(folder)/'fonts').exists())

    def test_fonts_must_match_approved_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            jar=Path(folder)/'input.jar'
            with zipfile.ZipFile(jar,'w') as archive: archive.writestr('BOOT-INF/classes/static/fonts/sample.ttf',b'synthetic')
            profile={'fonts':[{'path':'/usr/share/fonts/truetype/sample.ttf','bytes':9,'sha256':hashlib.sha256(b'synthetic').hexdigest()}]}
            extract_fonts(jar,Path(folder)/'fonts',profile)
            self.assertEqual((Path(folder)/'fonts/sample.ttf').read_bytes(),b'synthetic')
            profile['fonts'][0]['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'checksum'):
                extract_fonts(jar,Path(folder)/'bad-fonts',profile)


if __name__=='__main__': unittest.main()
