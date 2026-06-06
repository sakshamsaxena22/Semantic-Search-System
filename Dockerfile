FROM python:3.11-slim

# Install system dependencies (Tesseract OCR + Poppler for PDF images)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV HF_HOME=/app/.cache/huggingface

# Install CPU-only PyTorch to save RAM and disk space (prevents CUDA packages from loading)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy & install Python dependencies first (layer cache)
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download ML models so they are cached inside the container image
RUN python -m spacy download en_core_web_sm
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copy project source
COPY . .

# Ensure upload folder exists
RUN mkdir -p backend/data

# Use PORT env var (Railway / Render inject this)
ENV PORT=5000

EXPOSE 5000

# Run via gunicorn — 1 worker, preload to share memory, bind to $PORT
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --preload backend.app.main:app
