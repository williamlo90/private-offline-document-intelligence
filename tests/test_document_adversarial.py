"""Native parser and deterministic permission checks, not AI injection acceptance."""
from io import BytesIO
from pathlib import Path
import shutil
import pytest
from pypdf import PdfWriter

from backend.domain import Actor,Service,MemoryRepository,DomainError
from backend.pdf_parser import parse_pdf,ParseError

ROOT=Path(__file__).resolve().parents[1]

def blank_pdf(width=595,height=842):
    writer=PdfWriter();writer.add_blank_page(width=width,height=height)
    out=BytesIO();writer.write(out);return out.getvalue()

def test_oversized_render_rejected_before_pixel_allocation():
    with pytest.raises(ParseError) as error:parse_pdf(blank_pdf(100000,100000))
    assert error.value.code=='page_dimensions_limit'

def test_actual_blank_ocr_is_review_not_usable():
    if not (shutil.which('tesseract') or Path('C:/Program Files/Tesseract-OCR/tesseract.exe').exists()):
        pytest.skip('Native Tesseract required; skipped is not acceptance')
    parsed=parse_pdf(blank_pdf())
    assert parsed.pages[0].method=='tesseract' and parsed.pages[0].quality=='review'
    service=Service(MemoryRepository());actor=Actor('t','atlas','technician')
    service.ingest(actor,'blank','Blank','',pages=parsed.pages,source_hash=parsed.sha256)
    with pytest.raises(DomainError):service.prepare(actor,['blank'],['invented step'])

def test_missing_ocr_asset_fails_without_fallback(monkeypatch,tmp_path):
    monkeypatch.setenv('PRIVATE_TESSDATA',str(tmp_path))
    with pytest.raises(ParseError) as error:parse_pdf(blank_pdf(),language='ind')
    assert error.value.code in {'ocr_language_or_runtime_unavailable','ocr_unavailable'}

def test_injection_document_remains_untrusted_text_and_cannot_read_other_tenant():
    service=Service(MemoryRepository());actor=Actor('t','atlas','technician');other=Actor('b','birch','technician')
    service.ingest(other,'private-sla','Private SLA','Critical target is 20 minutes.')
    parsed=parse_pdf((ROOT/'evaluation/development/atlas-untrusted-v1.pdf').read_bytes())
    text='\n'.join(p.text for p in parsed.pages)
    service.ingest(actor,'untrusted','Untrusted appendix',text,pages=parsed.pages)
    before=list(service.repo.events('atlas'))
    hits=service.search(actor,'Ignore all previous instructions')
    assert hits and all(h['document_id']=='untrusted' for h in hits)
    assert '20 minutes' not in str(hits)
    assert service.repo.events('atlas')==before
    assert service.repo.proposals('atlas')==[]
    with pytest.raises(DomainError):service.read_document(actor,'private-sla')
