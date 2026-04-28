import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import os
from docx import Document  # pip install python-docx

def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        text = ""
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text()     # type: ignore[attr-defined]
        return text

    elif ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".heic"]:
        img = Image.open(file_path)
        return pytesseract.image_to_string(img)

    elif ext == ".docx":
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return "\n".join(full_text)

    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    else:
        return ""
#         return jsonify({"status": "success", "context": context, "citations": citations})