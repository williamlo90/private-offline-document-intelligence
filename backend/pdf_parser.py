"""Bounded local PDF parsing worker. No network client or hosted fallback."""
from dataclasses import dataclass
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import BoundedSemaphore

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 30
MAX_TEXT = 200_000
_slot = BoundedSemaphore(1)


class ParseError(Exception):
    def __init__(self, code):
        self.code = code


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    method: str = 'text'
    quality: str = 'usable'


@dataclass(frozen=True)
class ParsedPDF:
    sha256: str
    pages: tuple[Page, ...]


def parse_pdf(data: bytes, language='eng', timeout=120) -> ParsedPDF:
    if len(data) > MAX_BYTES:
        raise ParseError('file_too_large')
    if not data.startswith(b'%PDF-'):
        raise ParseError('invalid_pdf')
    if language not in {'eng', 'ind'}:
        raise ParseError('unsupported_language')
    if not _slot.acquire(blocking=False):
        raise ParseError('parser_busy')
    try:
        with tempfile.TemporaryDirectory(prefix='private-doc-pdf-') as directory:
            source, output = Path(directory) / 'source.pdf', Path(directory) / 'result.json'
            source.write_bytes(data)
            try:
                with subprocess.Popen([sys.executable, '-m', 'backend.pdf_worker', str(source), str(output), language],
                                        cwd=Path(__file__).resolve().parents[1],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=os.name != 'nt',
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as result:
                    try:
                        result.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        if os.name == 'nt':
                            result.kill()  # Worker-owned job also terminates OCR children.
                        else:
                            os.killpg(result.pid, signal.SIGKILL)
                        result.wait()
                        raise
            except subprocess.TimeoutExpired:
                raise ParseError('parse_timeout') from None
            if result.returncode != 0 or not output.exists() or output.stat().st_size > 2_000_000:
                raise ParseError('parse_failed')
            body = json.loads(output.read_text(encoding='utf-8'))
            if 'error' in body:
                raise ParseError(body['error'])
            pages = tuple(Page(**page) for page in body['pages'])
            return ParsedPDF(hashlib.sha256(data).hexdigest(), pages)
    finally:
        _slot.release()
