from pathlib import Path
import pytest
from reportlab.pdfgen import canvas
from smartppt.config import Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTHONPATH', str(Path(__file__).resolve().parents[1]/'src'))
    monkeypatch.setenv('SMARTPPT_DATA', str(tmp_path/'jobs'))
    return Settings(root=tmp_path/'jobs')


@pytest.fixture
def pdf_file(tmp_path):
    path=tmp_path/'source.pdf'
    c=canvas.Canvas(str(path), pagesize=(720,405))
    c.setFont('Helvetica',20);c.drawString(40,340,'Revenue 2026: $12,345.67')
    c.setFont('Helvetica',12);c.drawString(40,300,'Editable text and a simple table.')
    c.line(40,280,640,280);c.drawString(40,250,'North 100  South 200')
    c.showPage();c.drawString(40,340,'Second page, same order.');c.save()
    return path
