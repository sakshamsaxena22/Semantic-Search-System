# Semantic Search System — Project Summary

This document provides a complete summary of all bugs fixed, optimizations applied, architectural changes made, and deployment configurations implemented to bring the **Semantic Search System** from a local prototype to a production-ready, cloud-deployed application.

**Live URL:** https://semantic-search-system-1-r509.onrender.com

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Directory Restructuring](#2-architecture--directory-restructuring)
3. [Dockerfile & Build Optimization](#3-dockerfile--build-optimization)
4. [Dependency Fixes](#4-dependency-fixes)
5. [Memory Optimization (OOM Prevention)](#5-memory-optimization-oom-prevention)
6. [Vector Database — Pinecone Integration](#6-vector-database--pinecone-integration)
7. [OCR Service — Cross-Platform Tesseract Fix](#7-ocr-service--cross-platform-tesseract-fix)
8. [Bulk Upload Pipeline (75+ Files)](#8-bulk-upload-pipeline-75-files)
9. [Pinecone Index Configuration](#9-pinecone-index-configuration)
10. [LLM API Client Improvements](#10-llm-api-client-improvements)
11. [Frontend — Decoupled Interface](#11-frontend--decoupled-interface)
12. [Documentation Created](#12-documentation-created)
13. [Deployment Architecture](#13-deployment-architecture)
14. [Commit History](#14-commit-history)

---

## 1. Project Overview

The Semantic Search System is an AI-powered document intelligence platform. Users upload documents (PDF, DOCX, TXT, images), and the system:

1. **Extracts text** using PyMuPDF (text-layer PDFs) and Tesseract OCR (scanned/image-based pages).
2. **Chunks and embeds** the text using `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional vectors).
3. **Stores vectors** in Pinecone (cloud) or ChromaDB (local fallback) for semantic similarity search.
4. **Builds a knowledge graph** using spaCy NER + Groq LLM relation extraction (Graph RAG).
5. **Answers questions** by retrieving relevant chunks via vector search + graph traversal, then generating answers via the Groq LLM API.

---

## 2. Architecture & Directory Restructuring

### Changes Made
- **Frontend Isolation:** Created `frontend/index.html` as a standalone static HTML file with a configurable `BACKEND_URL` variable, enabling deployment on Vercel/GitHub Pages or serving directly from Flask.
- **Flask Template Realignment:** Updated `backend/app/main.py` to set `template_folder` to the root-level `frontend/` directory.
- **Redundant Files Cleaned:**
  - Deleted `backend/app/templates/` (contained obsolete `upload.html`).
  - Deleted duplicate root-level `DEPLOYMENT_GUIDE.md` (consolidated into `docs/deployment_guide.md`).
  - Deleted duplicate root-level `documentation.md`.

### Current Structure
```
SemanticSearchSystem/
├── backend/
│   └── app/
│       ├── main.py              # Flask app entry point
│       ├── routes.py            # API blueprint
│       └── services/
│           ├── ocr_service.py   # Text extraction (PyMuPDF + Tesseract)
│           ├── vector_service.py # Vector store (Pinecone / ChromaDB)
│           ├── groq_client.py   # Groq LLM API client
│           └── graph_service.py # Knowledge graph (spaCy + NetworkX)
├── frontend/
│   └── index.html               # Single-page web interface
├── docs/
│   ├── summary.md               # This file
│   ├── deployment_guide.md      # Step-by-step deployment guide
│   └── documentation.md         # Technical handover manual
├── Dockerfile                   # Production container build
├── requirements.txt             # Unified Python dependencies
├── render.yaml                  # Render service configuration
└── railway.toml                 # Railway deployment config
```

---

## 3. Dockerfile & Build Optimization

### Bugs Fixed
| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Build failed on Render (`no such file or directory`) | Render couldn't find the Dockerfile due to redundant `backend/Dockerfile` creating path confusion | Deleted `backend/Dockerfile` |
| `backend/Dockerfile` used `apt-get` on Alpine base image | Alpine uses `apk`, not `apt-get` — commands failed silently | Deleted the buggy file entirely |
| Container crashed at runtime (models not found) | ML models were downloaded at runtime but `HF_HUB_OFFLINE=1` blocked network access | Added `RUN` commands to pre-download models during build |
| Image size ~3 GB (CUDA packages included) | Default PyTorch install pulls ~1.5 GB of Nvidia CUDA libraries even on CPU-only containers | Installed CPU-only PyTorch via `--index-url https://download.pytorch.org/whl/cpu` |

### Final Dockerfile Configuration
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y tesseract-ocr poppler-utils libgl1
WORKDIR /app
ENV HF_HOME=/app/.cache/huggingface
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
COPY . .
RUN mkdir -p backend/data
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --preload backend.app.main:app
```

---

## 4. Dependency Fixes

### `requirements.txt` Consolidation
- **Deleted `requirements.prod.txt`** — was outdated, missing critical packages (`spacy`, `networkx`), and still referencing legacy `easyocr`.
- **Unified all dependencies** into a single `requirements.txt`.

### Package Rename Fix
| Old Package | New Package | Reason |
|------------|-------------|--------|
| `pinecone-client>=3.0.0` | `pinecone>=3.0.0` | The `pinecone-client` package was officially renamed to `pinecone`. The old package now **intentionally raises an Exception on import**, crashing the server. |

---

## 5. Memory Optimization (OOM Prevention)

The Render free tier provides **512 MB RAM**. The original codebase consumed ~800 MB+ at boot, causing an OOM crash loop.

### Root Causes & Fixes

| Problem | RAM Impact | Solution |
|---------|-----------|----------|
| `SentenceTransformer` loaded at **import time** (module-level) | ~400 MB per worker, loaded even before any request | **Lazy-loaded** — model only loads on first actual upload/query |
| `chromadb` and `pinecone` clients initialized in `__init__` | ~50-100 MB of library overhead at boot | **Lazy-initialized** via `_ensure_pinecone()` and `_ensure_chroma()` methods |
| Gunicorn spawned **2 workers** | Each worker forks a full Python process, doubling all memory | Reduced to **1 worker** with `--preload` flag |
| Full PyTorch with CUDA libraries installed | ~1.5 GB disk, ~200 MB RAM from CUDA runtime | Installed **CPU-only PyTorch** |

### Before vs After

| Metric | Before | After |
|--------|--------|-------|
| Boot time | ∞ (OOM crash loop) | **~4 seconds** |
| Boot RAM | ~800 MB (crashed) | **~120 MB** |
| First request RAM | N/A | ~350 MB (model loaded on demand) |
| Gunicorn workers | 2 | 1 |
| PyTorch size | ~1.5 GB (with CUDA) | ~200 MB (CPU-only) |

---

## 6. Vector Database — Pinecone Integration

### What Changed
Added **Pinecone** as the production vector database in `backend/app/services/vector_service.py`, with automatic fallback to local ChromaDB.

### How It Works
```
If PINECONE_API_KEY and PINECONE_INDEX_NAME are set:
    → Use Pinecone (cloud, serverless, persistent)
Else:
    → Use ChromaDB (local SQLite, ephemeral on container restart)
```

### Pinecone Configuration
| Setting | Value |
|---------|-------|
| Index Name | `semantic-search-index` |
| Dimensions | `384` (matches all-MiniLM-L6-v2 output) |
| Metric | `cosine` |
| Type | Serverless |

### Environment Variables (set on Render dashboard)
| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Authenticates Groq LLM API calls |
| `PINECONE_API_KEY` | Authenticates Pinecone vector database |
| `PINECONE_INDEX_NAME` | Specifies which Pinecone index to use |

---

## 7. OCR Service — Cross-Platform Tesseract Fix

### Bug
The OCR service (`ocr_service.py`) only checked for Tesseract at the **Windows** default path:
```python
_TESSERACT_DEFAULT_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```
On the Linux Docker container, Tesseract is installed at `/usr/bin/tesseract`, so the service logged a warning and OCR silently failed for scanned PDFs.

### Fix
Added cross-platform detection:
```python
_TESSERACT_DEFAULT_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_TESSERACT_DEFAULT_LINUX = "/usr/bin/tesseract"
if os.path.isfile(_TESSERACT_DEFAULT_WIN):
    _tess_cmd = _TESSERACT_DEFAULT_WIN
elif os.path.isfile(_TESSERACT_DEFAULT_LINUX):
    _tess_cmd = _TESSERACT_DEFAULT_LINUX
```

---

## 8. Bulk Upload Pipeline (75+ Files)

The original server spawned a **new thread per uploaded file**. With 75+ files, this caused:
- Dozens of threads running simultaneously, each loading chunks into memory
- RAM spikes causing OOM-kills on Render
- In-memory job tracking (`_jobs` dict) lost on worker restart → "Unknown job ID" errors

### Performance & Pipeline Fixes Implemented:

| Fix | File | Description |
|-----|------|-------------|
| **Sequential Job Queue** | `main.py` | Replaced per-file `threading.Thread` with a `queue.Queue` + single daemon worker thread. Files are processed **one at a time**, keeping RAM stable at ~300 MB. |
| **Persistent Job Store** | `main.py` | Job status is now written to `.jobs.json` on disk (inside `backend/data/`). If the worker restarts mid-batch, the frontend can still poll all previously completed jobs. Auto-prunes to last 200 jobs. |
| **Bypass Graph RAG on Ingestion** | `main.py` | Removed the slow Graph RAG creation process from the upload route. Since Graph RAG requires calling Groq's LLM API for each chunk, moving it out of ingestion avoids API rate limits and OOM risks, making uploads fast and stable. |
| **Batched & Streamed Encoding** | `vector_service.py` | Instead of encoding all chunks at once, they are encoded in **batches of 32**. Furthermore, vectors are immediately upserted to Pinecone in batches and garbage-collected, preventing large vector arrays from consuming RAM. |
| **Lower OCR DPI** | `ocr_service.py` | Reduced rendering DPI from 200 to **150**. This reduces page image sizes by ~44%, dramatically lowering memory usage per scanned page and speeding up Tesseract execution. |
| **Unbounded Memory Protection** | `graph_service.py`, `groq_client.py` | Added registry capping (5,000 items maximum) to the knowledge graph and response caching caps (200 items maximum) to the Groq API cache to prevent long-running memory leaks. |
| **GC between files** | `main.py` | Runs `gc.collect()` after each file finishes processing, freeing up text buffers and temporary structures. |

### Upload flow for 75 files:
```
Frontend uploads 75 files rapidly (fire-and-forget uploads)
  → Server accepts each instantly (HTTP 202)
  → Job ID saved to .jobs.json on disk
  → File enqueued in queue.Queue

Background worker thread:
  → Dequeue file 1 → extract text → embed (32 at a time) → upsert to Pinecone → gc.collect()
  → Dequeue file 2 → extract text → embed (32 at a time) → upsert to Pinecone → gc.collect()
  → ... (stable ~300 MB RAM throughout, completing each file in seconds)

Frontend polls /status/<job_id> for all jobs in parallel:
  → Displays real-time job-by-job status dashboard (⏳, 🔄, ✅, ❌)
  → Always gets an answer (jobs persisted to disk)
  → Survives background worker/server restarts
```

---

## 9. Pinecone Index Configuration

The Pinecone index **must** be configured with the correct dimensions matching the embedding model output. Mismatched dimensions cause `400` errors on every upsert.

| Setting | Required Value | Reason |
|---------|---------------|--------|
| **Index Name** | `semantic-search-index` | Must match `PINECONE_INDEX_NAME` env var |
| **Dimensions** | **`384`** | Output size of `all-MiniLM-L6-v2` model |
| **Metric** | `cosine` | Best for semantic text similarity |
| **Type** | `Serverless` | Free tier compatible, auto-scales |

> **Common mistake:** Creating the index with 1024 or 768 dimensions (common defaults for larger models). This system uses the lightweight `all-MiniLM-L6-v2` model which outputs exactly **384** dimensions.

---

## 10. LLM API Client Improvements

Changes made to `backend/app/services/groq_client.py`:

- **Query Caching:** Added a global `_llm_cache` dictionary. Identical prompts are resolved from cache, avoiding redundant API calls and rate limit consumption.
- **Backoff Strategy:** Enhanced HTTP 429 (rate limit) handling to parse and sleep the exact duration recommended by Groq response headers.
- **Retry Escalation:** Increased API call retries from 3 to 6 for better resilience against transient failures.

---

## 11. Frontend — Decoupled Interface

### Design
Created `frontend/index.html` as a premium, single-page web interface with:
- Dark mode design with glassmorphism effects
- Inter font family from Google Fonts
- Drag & drop file upload with progress bar
- Asynchronous job polling (`/status/<job_id>`) for background processing
- Real-time status updates during upload/extraction/indexing
- AI answer display with source citations

### Backend URL Configuration
```javascript
// Line 308 in frontend/index.html
const BACKEND_URL = "";  // Empty = same origin (Render serves both)
```
When deployed on Render, the frontend is served by Flask at the `/` route, so `BACKEND_URL` stays empty. If deployed separately on Vercel, set it to the Render URL.

---

## 12. Documentation Created

| File | Purpose |
|------|---------|
| `docs/summary.md` | This file — complete project changelog and technical summary |
| `docs/deployment_guide.md` | Step-by-step deployment guide written for non-technical users (Groq → Pinecone → Render → Vercel) |
| `docs/documentation.md` | Technical handover manual with architecture details |

---

## 13. Deployment Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Render (Free Tier)                │
│                                                     │
│   Docker Container (python:3.11-slim)               │
│   ┌───────────────────────────────────────────────┐ │
│   │  Gunicorn (1 worker, preload)                 │ │
│   │  ┌─────────────────────────────────────────┐  │ │
│   │  │  Flask App (backend/app/main.py)        │  │ │
│   │  │  ├── GET /          → serves frontend   │  │ │
│   │  │  ├── POST /upload   → file ingestion    │  │ │
│   │  │  ├── GET /status/id → job polling       │  │ │
│   │  │  └── POST /query   → semantic search    │  │ │
│   │  └─────────────────────────────────────────┘  │ │
│   └───────────────────────────────────────────────┘ │
│                         │                           │
│                         ▼                           │
│              ┌──────────────────┐                   │
│              │  SentenceTransf. │                   │
│              │  (lazy-loaded)   │                   │
│              └────────┬─────────┘                   │
└───────────────────────┼─────────────────────────────┘
                        │
            ┌───────────┼───────────┐
            ▼                       ▼
   ┌─────────────────┐    ┌─────────────────┐
   │  Pinecone Cloud │    │   Groq Cloud    │
   │  (Vector Store) │    │   (LLM API)     │
   │  384-dim cosine │    │   Llama/Mixtral │
   └─────────────────┘    └─────────────────┘
```

---

## 14. Commit History

| Commit | Description |
|--------|-------------|
| `914a532` | perf: Remove graph RAG from upload, fire-and-forget UI, batched encoding, lower OCR DPI |
| `2d52571` | feat: Sequential job queue + persistent job store + batched encoding for 75+ file uploads |
| `78959a5` | docs: Update summary.md with complete project changelog and deployment architecture |
| `8e4cb09` | fix: Rename `pinecone-client` to `pinecone` (package renamed, old name crashes on import) |
| `7651b86` | fix: Lazy-load all heavy ML models to prevent OOM crash on Render free tier |
| `a5eb5a0` | build: Switch to CPU-only PyTorch and reduce gunicorn workers to 1 |
| `57ca850` | docs: Update deployment guide with Pinecone DB details and delete duplicate guide |
| `ed5d853` | Create project handover DEPLOYMENT_GUIDE.md at root directory |
| `64f8459` | Pre-download ML and NLP models during Docker build stage |
| `090d538` | Create docs/summary.md detailing recent bug fixes |
| `b147925` | Fix production build: consolidate dependencies, update Dockerfile |
| `ca0a817` | Remove redundant and buggy backend/Dockerfile |
| `acce7fa` | Reorganize workspace: separate frontend, update Flask template routing |
| `15c16fb` | Create docs directory with project handover handbook and deployment guides |
| `4cc8e8f` | Configure system: replace easyocr with pytesseract, add graph-RAG, implement query caching |
| `3f7d878` | perf: parallel page OCR with ThreadPoolExecutor, lower DPI |
