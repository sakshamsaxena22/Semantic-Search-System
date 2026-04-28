"""
OCR / text-extraction service.

Extraction strategy per file type
──────────────────────────────────
PDF   : Two-pass per page —
          1. PyMuPDF get_text()  → fast, perfect for text-layer PDFs
          2. If page has < 20 native chars (image-based / scanned),
             render page to image → EasyOCR.
        Image-only pages are processed IN PARALLEL for speed.
DOCX  : python-docx paragraph extraction
TXT   : plain read
Images: EasyOCR directly (JPG / PNG / BMP / TIFF)

EasyOCR is lazily initialised on first use.
"""

import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz          # PyMuPDF
import numpy as np
from docx import Document
from PIL import Image

# ── Lazy EasyOCR reader (initialised once, reused) ────────────────────────────
_easyocr_reader = None


def _get_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        logging.info("Initialising EasyOCR reader…")
        _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        logging.info("EasyOCR reader ready.")
    return _easyocr_reader


# ── Tuning knobs ──────────────────────────────────────────────────────────────
_OCR_DPI       = 150    # lower = faster render; raise to 200 for tiny text
_MIN_TEXT_CHARS = 20    # pages below this are treated as image-only
_MAX_WORKERS   = 4      # parallel OCR threads for multi-page image PDFs


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ocr_image(pil_img: Image.Image) -> str:
    """Run EasyOCR on a PIL image and return joined text."""
    reader = _get_reader()
    arr = np.array(pil_img.convert("RGB"))
    results = reader.readtext(arr, detail=0, paragraph=True)
    return "\n".join(results)


def _render_and_ocr_page(page: fitz.Page, page_num: int) -> tuple[int, str]:
    """Render a single PDF page and OCR it. Returns (page_num, text)."""
    zoom = _OCR_DPI / 72
    mat  = fitz.Matrix(zoom, zoom)
    pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img  = Image.open(io.BytesIO(pix.tobytes("png")))
    text = _ocr_image(img).strip()
    logging.info("Page %d: EasyOCR extracted %d chars", page_num, len(text))
    return page_num, text


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text_from_file(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    # ── PDF ───────────────────────────────────────────────────────────────────
    if ext == ".pdf":
        doc = fitz.open(file_path)
        native_texts: dict[int, str] = {}
        ocr_needed: list[tuple[int, fitz.Page]] = []

        # Pass 1 — collect native text; identify image-only pages
        for page_num, page in enumerate(doc, start=1):
            native = page.get_text().strip()          # type: ignore[attr-defined]
            if len(native) >= _MIN_TEXT_CHARS:
                native_texts[page_num] = native
                logging.debug("Page %d: native text (%d chars)", page_num, len(native))
            else:
                ocr_needed.append((page_num, page))
                logging.info("Page %d: no native text → queued for OCR", page_num)

        # Pass 2 — OCR image pages in parallel
        ocr_results: dict[int, str] = {}
        if ocr_needed:
            logging.info("Running EasyOCR on %d page(s) in parallel…", len(ocr_needed))
            with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(ocr_needed))) as pool:
                futures = {
                    pool.submit(_render_and_ocr_page, page, pnum): pnum
                    for pnum, page in ocr_needed
                }
                for future in as_completed(futures):
                    pnum, text = future.result()
                    ocr_results[pnum] = text

        doc.close()

        # Merge in original page order
        total_pages = len(native_texts) + len(ocr_results)
        all_texts = []
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