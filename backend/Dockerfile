FROM python:3.10-alpine3.21
WORKDIR /app
COPY . .
RUN apt-get update && \
    apt-get install -y poppler-utils tesseract-ocr && \
    pip install --no-cache-dir -r requirements.txt
CMD ["python", "app/main.py"]