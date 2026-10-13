"""Generate one synthetic image-only PDF for connected OCR acceptance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "local/phase-7/atlas-restore-scan.pdf"
MANIFEST = ROOT / "local/phase-7/atlas-restore-scan.json"
LINES = [
    "Atlas restore rehearsal desk card",
    "ATLAS / SOP / synthetic local source",
    "Record rehearsal ticket R-731 and storage",
    "checksum C-88 before manager review.",
    "Check the approved maintenance ticket.",
    "Never restore production data in rehearsal.",
]


def main() -> None:
    if OUT.exists() or MANIFEST.exists():
        raise RuntimeError("Refusing to replace frozen scan fixture")
    image = Image.new("RGB", (1700, 2200), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 58)
    for index, line in enumerate(LINES):
        draw.text((100, 130 + index * 110), line, font=font, fill="black")
    document = canvas.Canvas(str(OUT), pagesize=(612, 792))
    document.drawImage(ImageReader(image), 0, 0, width=612, height=792)
    document.showPage()
    document.save()
    assert not (PdfReader(str(OUT)).pages[0].extract_text() or "").strip()
    result = {"source": "synthetic generated image-only PDF", "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
              "bytes": OUT.stat().st_size, "expected_text": LINES,
              "pdf_text_layer": False}
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("sha256", "bytes", "pdf_text_layer")}))


if __name__ == "__main__":
    main()
