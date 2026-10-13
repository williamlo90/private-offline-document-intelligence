"""Verify existing synthetic scans using pre-provisioned local OCR inside an offline namespace."""
import json
from pathlib import Path
import socket
import subprocess
from backend.pdf_parser import parse_pdf

if sorted(name for _,name in socket.if_nameindex())!=['lo']:
    raise RuntimeError('Run only inside a loopback-only Linux network namespace')
root=Path(__file__).resolve().parents[1]
results=[]
for name,language,phrase in [('atlas-backup-v1','eng','Open the local backup console'),
                             ('birch-disk-v1','ind','kurang dari 15 persen')]:
    scan=root/'local/phase-2'/f'{name}-scan.pdf'
    parsed=parse_pdf(scan.read_bytes(),language)
    if not parsed.pages or parsed.pages[0].method!='tesseract' or phrase.lower() not in parsed.pages[0].text.lower():
        raise RuntimeError('Offline OCR output failed source expectation')
    results.append({'source':name,'language':language,'sha256':parsed.sha256,'quality':parsed.pages[0].quality})
version=subprocess.check_output(['/home/william/project07-lab-runtime/usr/bin/tesseract','--version'],text=True).splitlines()[0]
report={'status':'passed','boundary':'isolated Linux namespace, loopback only','ocr_runtime':version,
        'results':results,'scope':'Two synthetic scans using pre-provisioned OCR executable and project language data'}
(root/'local/phase-5/offline-ocr.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
