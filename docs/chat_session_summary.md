# Chat Session Summary: Performance Optimization & Reliability Enhancements

This document summarizes the recent debugging and optimization session aimed at fixing slow PDF uploads and ensuring the system could handle 75+ document uploads concurrently without crashing.

## Issues Addressed

1. **Slow PDF Uploads**:
   - The user reported that a 2-page PDF was taking 1-2 minutes to upload and index.
   - **Root Cause Analysis**: While PyMuPDF was successfully extracting native text from PDFs, the pipeline was redundantly converting PDF pages to images (`pdf2image`) and running Tesseract OCR on them. Tesseract is CPU-intensive and slow, causing the massive bottleneck.

2. **Large Batch Uploads Failing**:
   - The user needed the system to reliably handle 75+ files at once within a strict 512MB RAM limit on Render.
   - **Root Cause Analysis**: The system was previously creating a new thread for every uploaded file and concurrently processing them (including generating embeddings and parsing OCR). This caused severe Out-of-Memory (OOM) crashes on the server.

## Solutions Implemented

### 1. PDF OCR Bypass
- Modified `ocr_service.py` to completely bypass `pdf2image` and Tesseract OCR for all PDF files. 
- The system now exclusively uses `PyMuPDF` for instantaneous native text extraction from PDFs. Tesseract is reserved strictly for standalone image formats (`.png`, `.jpg`, etc.).
- **Result**: PDF upload times dropped from minutes to a few seconds.

### 2. Sequential Job Queue & Background Processing
- Replaced the concurrent threading model in `main.py` with a sequential `queue.Queue` and a single daemon worker thread.
- Files uploaded in parallel are now queued and processed strictly one-by-one in the background.
- Added a persistent JSON store (`.jobs.json`) to track the status (`queued`, `processing`, `done`, `failed`) of every file.

### 3. Memory & Performance Optimizations
- **Batched Vector Upserts**: Changed the SentenceTransformer integration to encode and upsert text chunks in batches of 32, immediately garbage-collecting the memory afterwards.
- **Removed GraphRAG at Upload**: Disabled the Knowledge Graph ingestion during the file upload phase. Entity extraction and graph expansion now only occur at search time, drastically reducing CPU/RAM usage during ingestion.

### 4. Frontend Status Dashboard
- Created a live status dashboard in `index.html` that polls a new `/status` endpoint to show real-time progress of each uploaded file.
- Removed the 100-file upload limit on the frontend dropzone.

## Conclusion
The system is now highly resilient, memory-efficient, and fast. It seamlessly processes 75+ files in the background sequentially while providing instantaneous feedback to the user, strictly adhering to the 512MB RAM constraint.
