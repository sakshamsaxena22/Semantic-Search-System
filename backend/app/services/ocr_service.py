"""
OCR / text-extraction service.

Extraction strategy per file type
──────────────────────────────────
PDF   : Two-pass per page —
          1. PyMuPDF get_text()  → fast, perfect for text-layer PDFs
          2. If page has < 20 native chars (image-based / scanned),
             render page to image → EasyOCR (pure-Python, no binary needed)
DOCX  : python-docx paragraph extraction
TXT   : plain read
Images: EasyOCR directly (JPG / PNG / BMP / TIFF)

EasyOCR is lazily initialised on first use so cold-start only happens
when an image-based document is actually processed.
"""

import io
import logging
import os

import fitz          # PyMuPDF
import numpy as np
from docx import Document
from PIL import Image

# ── Lazy EasyOCR reader (initialised once, reused) ────────────────────────────
_easyocr_reader = None


def _get_reader():
    """Return a cached EasyOCR Reader instance (English)."""
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        logging.info("Initialising EasyOCR reader (first use — may take a few seconds)…")
        _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        logging.info("EasyOCR reader ready.")
    return _easyocr_reader


# Resolution used when rasterising a PDF page for OCR (higher = better accuracy)
_OCR_DPI = 200
_MIN_TEXT_CHARS = 20     # pages below this threshold are treated as image-only


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ocr_image(pil_img: Image.Image) -> str:
    """Run EasyOCR on a PIL image and return joined text."""
    reader = _get_reader()
    arr = np.array(pil_img.convert("RGB"))
    results = reader.readtext(arr, detail=0, paragraph=True)
    return "\n".join(results)


def _render_page_to_pil(page: fitz.Page, dpi: int = _OCR_DPI) -> Image.Image:
    """Render a PDF page to a PIL Image at the given DPI."""
    zoom = dpi / 72          # 72 pt = 1 inch baseline
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return Image.open(io.BytesIO(pix.tobytes("png")))


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text_from_file(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    # ── PDF ───────────────────────────────────────────────────────────────────
    if ext == ".pdf":
        pages_text = []
        doc = fitz.open(file_path)

        for page_num, page in enumerate(doc, start=1):
            native = page.get_text().strip()          # type: ignore[attr-defined]

            if len(native) >= _MIN_TEXT_CHARS:
                # Real text layer — use directly, fast path
                pages_text.append(native)
                logging.debug("Page %d: native text (%d chars)", page_num, len(native))
            else:
                # Image-based page → rasterise → EasyOCR
                logging.info("Page %d: no native text — running EasyOCR…", page_num)
                pil_img = _render_page_to_pil(page)
                ocr_text = _ocr_image(pil_img).strip()
                pages_text.append(ocr_text)
                logging.info(
                    "Page %d: EasyOCR extracted %d chars", page_num, len(ocr_text)
                )

        doc.close()
        combined = "\n\n".join(t for t in pages_text if t)
        return combined

    # ── Standalone image files ────────────────────────────────────────────────
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".heic"):
        img = Image.open(file_path)
        return _ocr_image(img)

    # ── DOCX ──────────────────────────────────────────────────────────────────
    elif ext == ".docx":
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # ── Plain text ────────────────────────────────────────────────────────────
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    else:
        logging.warning("Unsupported file type: %s", ext)
        return ""