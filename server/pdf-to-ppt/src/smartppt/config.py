from dataclasses import dataclass, field
import os
from pathlib import Path


@dataclass
class Settings:
    root: Path = field(default_factory=lambda: Path(os.getenv('SMARTPPT_DATA', 'var')).resolve())
    max_bytes: int = 30 * 1024 * 1024
    max_pages: int = 200
    retention_seconds: int = 3600
    job_timeout: int = 600
    max_queue: int = 20
    adobe_id: str = field(default_factory=lambda: os.getenv('PDF_SERVICES_CLIENT_ID', ''))
    adobe_secret: str = field(default_factory=lambda: os.getenv('PDF_SERVICES_CLIENT_SECRET', ''))
    editable_provider: str = field(default_factory=lambda: os.getenv('SMARTPPT_EDITABLE_PROVIDER', 'adobe'))
    stirling_url: str = field(default_factory=lambda: os.getenv('SMARTPPT_STIRLING_URL', ''))
    stirling_key: str = field(default_factory=lambda: os.getenv('SMARTPPT_STIRLING_KEY', ''))
    layout_assistance: bool = field(default_factory=lambda: os.getenv('SMARTPPT_LAYOUT_ASSISTANCE', '0') == '1')
    orientation_runner: str = field(default_factory=lambda: os.getenv('SMARTPPT_ORIENTATION_RUNNER', ''))
    ocr_python: str = field(default_factory=lambda: os.getenv('SMARTPPT_OCR_PYTHON', ''))
    ocr_runner: str = field(default_factory=lambda: os.getenv('SMARTPPT_OCR_RUNNER', ''))
    ocr_verifier_python: str = field(default_factory=lambda: os.getenv('SMARTPPT_OCR_VERIFIER_PYTHON', ''))
    ocr_verifier_runner: str = field(default_factory=lambda: os.getenv('SMARTPPT_OCR_VERIFIER_RUNNER', ''))
    oxr_python: str = field(default_factory=lambda: os.getenv('SMARTPPT_OXR_PYTHON', ''))
    oxr_runner: str = field(default_factory=lambda: os.getenv('SMARTPPT_OXR_RUNNER', ''))
    renderer_path: str = field(default_factory=lambda: os.getenv('SMARTPPT_RENDERER', ''))

    @property
    def local_ocr_available(self):
        return self.layout_assistance and Path(self.ocr_python).is_file() and Path(self.ocr_runner).is_file()

    @property
    def editable_available(self):
        if self.editable_provider == 'stirling':
            return bool(self.stirling_url)
        return self.editable_provider == 'adobe' and bool(self.adobe_id and self.adobe_secret)


class ConversionError(Exception):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)
