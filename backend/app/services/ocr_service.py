"""
OCR / text-extraction service.

Handles:
  - PDF  : native text first; falls back to Tesseract OCR per page when
            a page has no selectable text (i.e. it is image-based / scanned).
  - DOCX : paragraph text extraction via python-docx.
  - TXT  : plain read.
  - Images (JPG/PNG/BMP/TIFF) : Tesseract OCR directly.

Tesseract must be installed on the host:
  Windows → https://github.com/UB-Mannheim/tesseract/wiki
  Linux   → apt-get install tesseract-ocr
  macOS   → brew install tesseract
"""

import io
import logging
import os

import fitz  # PyMuPDF
import pytesseract
from docx import Document
from PIL import Image

# ── Tesseract binary path (Windows) ───────────────────────────────────────────
# pytesseract looks for `tesseract` on PATH by default.
# On Windows the installer places it here; set explicitly so it always works.
_WIN_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.name == "nt" and os.path.isfile(_WIN_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = _WIN_TESSERACT

# DPI used when rendering a PDF page to an image for OCR.
# 200 dpi is fast; raise to 300 for better accuracy on small text.
_OCR_DPI = 200
_MIN_TEXT_CHARS = 20   # pages with fewer chars are treated as image-only


def _ocr_pdf_page(page: fitz.Page) -> str:
    """Render a single PDF page to a PIL image and run Tesseract on it."""
    mat = fitz.Matrix(_OCR_DPI / 72, _OCR_DPI / 72)   # 72 pt = 1 inch
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img)


def _tesseract_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text_from_file(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    # ── PDF ───────────────────────────────────────────────────────────────────
    if ext == ".pdf":
        tess_ok = _tesseract_available()
        if not tess_ok:
            logging.warning(
                "Tesseract not found — OCR fallback disabled. "
                "Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki"
            )

        full_text = []
        doc = fitz.open(file_path)
        for page_num, page in enumerate(doc, start=1):
            native = page.get_text().strip()          # type: ignore[attr-defined]

            if len(native) >= _MIN_TEXT_CHARS:
                # Page has real selectable text — use it directly
                full_text.append(native)
                logging.debug("Page %d: native text (%d chars)", page_num, len(native))
            elif tess_ok:
                # Page is image-based — render + OCR
                ocr_text = _ocr_pdf_page(page).strip()
                full_text.append(ocr_text)
                logging.info(
                    "Page %d: no native text, OCR extracted %d chars",
                    page_num, len(ocr_text),
                )
            else:
                logging.warning(
                    "Page %d: no native text and Tesseract unavailable — skipped",
                    page_num,
                )

        doc.close()
        return "\n\n".join(full_text)

    # ── Standalone images ─────────────────────────────────────────────────────
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".heic"):
        img = Image.open(file_path)
        return pytesseract.image_to_string(img)

    # ── DOCX ──────────────────────────────────────────────────────────────────
    elif ext == ".docx":
        doc = Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())

    # ── Plain text ────────────────────────────────────────────────────────────
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    else:
        logging.warning("Unsupported file type: %s", ext)
        return ""