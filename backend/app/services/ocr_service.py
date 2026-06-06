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

import fitz          # PyMuPDF
import pytesseract
from docx import Document
from PIL import Image

# ── Tesseract binary path (Windows) ───────────────────────────────────────────
_TESSERACT_DEFAULT_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_tess_cmd = os.environ.get("TESSERACT_CMD", "")
if not _tess_cmd and os.path.isfile(_TESSERACT_DEFAULT_WIN):
    _tess_cmd = _TESSERACT_DEFAULT_WIN
if _tess_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tess_cmd
    logging.info("Tesseract binary: %s", _tess_cmd)
else:
    logging.warning(
        "Tesseract binary not found at default path. "
        "Set TESSERACT_CMD env-var or install Tesseract-OCR."
    )

# ── Tuning knobs ──────────────────────────────────────────────────────────────
_OCR_DPI        = 200   # DPI for PDF→image render; 200 gives good accuracy
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
        doc = fitz.open(file_path)
        native_texts: dict[int, str] = {}
        ocr_needed:   list[tuple[int, fitz.Page]] = []

        # Pass 1 — collect native text; identify image-only pages
        for page_num, page in enumerate(doc, start=1):
            native = page.get_text().strip()          # type: ignore[attr-defined]
            if len(native) >= _MIN_TEXT_CHARS:
                native_texts[page_num] = native
                logging.debug("Page %d: native text (%d chars)", page_num, len(native))
            else:
                ocr_needed.append((page_num, page))
                logging.info("Page %d: no native text → queued for OCR", page_num)

        # Pass 2 — OCR image pages sequentially (Tesseract is thread-safe but
        #          multiprocessing on Windows requires spawn which is slow)
        ocr_results: dict[int, str] = {}
        if ocr_needed:
            logging.info("Running Tesseract OCR on %d page(s)…", len(ocr_needed))
            for pnum, page in ocr_needed:
                _, text = _render_and_ocr_page(page, pnum)
                ocr_results[pnum] = text

        doc.close()

        # Merge in original page order
        total_pages = len(native_texts) + len(ocr_results)
        all_texts   = []
        for i in range(1, total_pages + 1):
            t = native_texts.get(i) or ocr_results.get(i, "")
            if t:
                all_texts.append(t)

        return "\n\n".join(all_texts)

    # ── Standalone image files ────────────────────────────────────────────────
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".heic"):
        return _ocr_image(Image.open(file_path))

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