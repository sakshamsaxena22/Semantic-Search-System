"""
OCR / text-extraction service.

Extraction strategy per file type
──────────────────────────────────
PDF   : Two-pass per page —
          1. PyMuPDF get_text()  → fast, perfect for text-layer PDFs
          2. If page has < 20 native chars (image-based / scanned),
             render page to image → PyTesseract OCR
DOCX  : python-docx paragraph extraction
TXT   : plain read
Images: PyTesseract directly (JPG / PNG / BMP / TIFF)

PyTesseract wraps the Tesseract-OCR binary. On Windows the binary is
expected at C:\\Program Files\\Tesseract-OCR\\tesseract.exe (default
installer location). Override by setting the TESSERACT_CMD env-var.
"""

import io
import logging
import os
import time

import fitz          # PyMuPDF
import pytesseract
from docx import Document
from PIL import Image

# ── Tesseract binary path ─────────────────────────────────────────────────────
_TESSERACT_DEFAULT_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_TESSERACT_DEFAULT_LINUX = "/usr/bin/tesseract"
_tess_cmd = os.environ.get("TESSERACT_CMD", "")
if not _tess_cmd:
    if os.path.isfile(_TESSERACT_DEFAULT_WIN):
        _tess_cmd = _TESSERACT_DEFAULT_WIN
    elif os.path.isfile(_TESSERACT_DEFAULT_LINUX):
        _tess_cmd = _TESSERACT_DEFAULT_LINUX
if _tess_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tess_cmd
    logging.info("Tesseract binary: %s", _tess_cmd)
else:
    logging.warning(
        "Tesseract binary not found at default path. "
        "Set TESSERACT_CMD env-var or install Tesseract-OCR."
    )

# ── Tuning knobs ──────────────────────────────────────────────────────────────
_OCR_DPI        = 150   # DPI for PDF→image render; 150 balances accuracy vs RAM/speed
_MIN_TEXT_CHARS = 20    # pages with fewer chars are treated as image-only
_TESS_CONFIG    = "--oem 3 --psm 3"   # LSTM engine + auto page-seg


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ocr_image(pil_img: Image.Image) -> str:
    """Run PyTesseract on a PIL image and return extracted text."""
    text = pytesseract.image_to_string(
        pil_img.convert("RGB"),
        config=_TESS_CONFIG,
    )
    return text.strip()


def _render_and_ocr_page(page: fitz.Page, page_num: int) -> tuple[int, str]:
    """Render a single PDF page to image and OCR it. Returns (page_num, text)."""
    zoom = _OCR_DPI / 72
    mat  = fitz.Matrix(zoom, zoom)
    pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img  = Image.open(io.BytesIO(pix.tobytes("png")))
    text = _ocr_image(img)
    logging.info("Page %d: Tesseract extracted %d chars", page_num, len(text))
    return page_num, text


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text_from_file(file_path: str) -> str:
    """
    Extract plain text from file_path.
    Supported: .pdf, .jpg, .jpeg, .png, .bmp, .tiff, .tif, .docx, .txt

    Returns a single string with all extracted text, pages separated by
    double newlines for PDF files.
    """
    ext = os.path.splitext(file_path)[1].lower()

    # ── PDF ───────────────────────────────────────────────────────────────────
    if ext == ".pdf":
        try:
            doc = fitz.open(file_path)
            all_texts = []
            for page in doc:
                try:
                    text = page.get_text().strip()
                    if text:
                        all_texts.append(text)
                except Exception as e:
                    logging.warning("Failed to extract text from page in %s: %s", file_path, e)
            doc.close()
            final_text = "\n\n".join(all_texts)
            if not final_text.strip():
                return "EXTRACTION_EMPTY"
            return final_text
        except Exception as e:
            logging.error("Failed to parse PDF %s: %s", file_path, e)
            return "EXTRACTION_EMPTY"

    # ── Standalone image files ────────────────────────────────────────────────
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".heic"):
        ocr_start = time.perf_counter()
        text = _ocr_image(Image.open(file_path))
        ocr_time = time.perf_counter() - ocr_start
        logging.info("TIMING AUDIT - Image OCR: %.4f sec", ocr_time)
        return text

    # ── DOCX ──────────────────────────────────────────────────────────────────
    elif ext == ".docx":
        doc = Document(file_path)
        texts = []
        for p in doc.paragraphs:
            if p.text.strip():
                texts.append(p.text.strip())
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip() and cell.text.strip() not in texts:
                        texts.append(cell.text.strip())
        return "\n".join(texts)

    # ── Plain text ────────────────────────────────────────────────────────────
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    else:
        logging.warning("Unsupported file type: %s", ext)
        return ""