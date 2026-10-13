"""Build two synthetic scanned fixtures and verify actual local Tesseract outputs."""
import hashlib
import json
import os
from pathlib import Path
import time

import pypdfium2 as pdfium
from pypdf import PdfReader
from backend.pdf_parser import parse_pdf

root = Path(__file__).resolve().parents[1]
out = root / 'local/phase-2'
out.mkdir(parents=True, exist_ok=True)
os.environ['PRIVATE_TESSDATA'] = str(root/'local/ocr/tessdata')
results = []
for filename, language, expected in [('atlas-backup-v1','eng','Open the local backup console'),('birch-disk-v1','ind','kurang dari 15 persen')]:
    doc = pdfium.PdfDocument(str(root/f'evaluation/development/{filename}.pdf'))
    rendered = doc[0].render(scale=300/72).to_pil().convert('RGB')
    scan = out/f'{filename}-scan.pdf'
    rendered.save(scan, 'PDF', resolution=300)
    assert not PdfReader(scan).pages[0].extract_text().strip(), 'Fixture must have no text layer'
    started = time.monotonic()
    parsed = parse_pdf(scan.read_bytes(), language)
    assert parsed.pages[0].method == 'tesseract'
    assert expected.lower() in parsed.pages[0].text.lower(), parsed.pages[0].text
    assert parsed.pages[0].quality == 'usable'
    preview = rendered.copy();preview.thumbnail((700,1000));preview.save(out/f'{filename}-scan.png')
    results.append({'source':filename,'language':language,'sha256':parsed.sha256,'ocr_seconds':round(time.monotonic()-started,3),'expected_phrase':expected,'status':'passed'})
assets = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'local/ocr/tessdata').glob('*.traineddata')}
result = {'results':results,'language_asset_sha256':assets,'runtime':'Tesseract 5.5.0.20241111','scope':'Two machine-rendered scan fixtures, actual local OCR. Not broad scan-quality or offline-egress acceptance.'}
(out/'native-ocr.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
