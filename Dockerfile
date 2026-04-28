FROM python:3.11-slim

# Install system dependencies (Tesseract OCR + Poppler for PDF images)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy & install Python dependencies first (layer cache)
COPY requirements.prod.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Ensure upload folder exists
RUN mkdir -p backend/data

# Use PORT env var (Railway / Render inject this)
ENV PORT=5000

EXPOSE 5000

# Run via gunicorn — 2 workers, bind to $PORT
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 backend.app.main:app
