# Semantic Search System: Enterprise Handover & Ownership Documentation

> **Status**: Official System of Record
> **Purpose**: Technical Due Diligence, Operations Handbook, and Complete Ownership Transfer Package.

---

## 1. Executive Summary & Product Architecture

### What it is
The Semantic Search System is an advanced Retrieval-Augmented Generation (RAG) platform. It allows users to upload unstructured documents (PDF, DOCX, Images) and perform natural-language queries against them.

### Why it exists
To provide highly accurate, context-aware answers across massive document sets by combining dense vector similarity search with explicit Knowledge Graph traversal, enabling "multi-hop" reasoning that traditional semantic search fails to achieve.

### How it works
The architecture is a Python monolithic application powered by Flask. It is divided into an asynchronous background ingestion pipeline (handling PyTorch encoding and NetworkX graph generation) and a synchronous API layer for querying. The system integrates closely with Pinecone (Vector DB) and the Groq API (LLM inference).

### Dependencies
* **Internal**: `backend/app/main.py`, `backend/app/config.py`
* **External**: Pinecone API, Groq API
* **Infrastructure**: Render.com, Docker, Gunicorn

### Risks & Common Failures
* **Risk**: Local ephemeral storage limits. Render free-tier wipes local disks unexpectedly.
* **Failure**: Loss of local state. If Render restarts the container, the local `.jobs.json` and `knowledge_graph.pkl` are permanently deleted.

### Troubleshooting
* If the server restarts, check the Gunicorn startup logs. Pinecone connection failures will print `WARNING:root:Startup check: Pinecone env vars MISSING`.

### Future Improvements
* Migrate the Knowledge Graph from local `NetworkX` `.pkl` files to a hosted Graph Database (e.g., Neo4j) to prevent data loss on container restarts.

> #### Verification & Citations
> * **Accuracy Verified**: Yes.
> * **Source Files**: `D:/SemanticSearchSystem/backend/app/main.py`, `D:/SemanticSearchSystem/backend/app/config.py`
> * **Relevant Functions**: `app.run()`, `VectorStore()` instantiation.
> * **Uncertainties**: None regarding the architecture design.

---

## 2. Asynchronous Queue & Thread Management

### What it is
A bespoke, in-memory asynchronous job processing system built directly into the Flask application, circumventing the need for external brokers like Redis/Celery.

### Why it exists
To operate within extremely strict memory constraints (512 MB RAM). Running PyTorch operations (SentenceTransformers) concurrently on multiple HTTP requests would immediately trigger OOM (Out of Memory) kills. A strict sequential queue guarantees only one document is processed at a time.

### How it works
When a file is POSTed to `/upload`, the Flask controller saves the file to disk, writes a `processing` status to `.jobs.json`, and adds the file path to a `queue.Queue()`. 
Upon the *first* HTTP request, an `@app.before_request` hook injects a `_queue_worker` background thread into the live Gunicorn worker process. This thread runs an infinite loop, popping items off the queue and executing them sequentially. A secondary `_worker_watchdog` thread monitors the primary thread and respawns it if it dies.

### Dependencies
* **Internal**: `backend/app/main.py`
* **Core Libraries**: `threading`, `queue`, `json`

### Risks & Common Failures
* **Risk**: Thread lockups. PyTorch or PyMuPDF can occasionally hang indefinitely without throwing an exception.
* **Failure**: The queue halts entirely, and all new uploads remain permanently stuck in "processing".

### Troubleshooting
* Monitor the `GET /health` endpoint. If `worker_alive` is false or `queue_size` continuously grows without `jobs_done` increasing, the worker has deadlocked. Restart the container.

### Future Improvements
* Refactor to use a lightweight disk-backed queue (e.g., SQLite/Celery) if horizontal scaling across multiple instances is ever required.

> #### Verification & Citations
> * **Accuracy Verified**: Yes.
> * **Source Files**: `D:/SemanticSearchSystem/backend/app/main.py`
> * **Relevant Functions**: `_queue_worker()`, `_worker_watchdog()`, `start_threads()`
> * **Uncertainties**: Exact edge cases where `_worker_thread.is_alive()` returns True despite a deadlock inside `model.encode()`.

---

## 3. Data Ingestion & OCR Pipeline

### What it is
A multi-format text extraction pipeline capable of parsing PDFs, images, and Microsoft Word documents into raw UTF-8 strings.

### Why it exists
RAG applications require high-fidelity raw text. Standard libraries often fail to capture nuanced document features like text boxes, headers, or embedded images.

### How it works
The `extract_text_from_file()` router inspects the file extension. 
* **PDFs**: Extracted page-by-page using `fitz` (PyMuPDF).
* **Images**: Processed visually using `pytesseract`.
* **DOCX**: Unzips the raw `.docx` archive and manually iterates through every underlying `word/*.xml` file using `xml.etree.ElementTree` to guarantee the extraction of text boxes, headers, footers, and shapes (bypassing the limitations of the `python-docx` library).

### Dependencies
* **Internal**: `backend/app/services/ocr_service.py`
* **External Core**: `pymupdf`, `pytesseract`, `Pillow`, `zipfile`
* **System Level**: `tesseract-ocr`, `poppler-utils` (installed via Dockerfile).

### Risks & Common Failures
* **Risk**: Corrupted or heavily encrypted files.
* **Failure**: Returns `EXTRACTION_EMPTY`, causing the job to safely fail rather than crash the system.

### Troubleshooting
* Check the backend logs for `[WORKER FAILED: <filename>]`. If DOCX extraction fails, verify the document is a valid XML-based DOCX and not a legacy binary `.doc`.

### Future Improvements
* Add Vision-Language Models (VLM) for processing complex PDF tables that `fitz` flattens into unreadable text.

> #### Verification & Citations
> * **Accuracy Verified**: Yes.
> * **Source Files**: `D:/SemanticSearchSystem/backend/app/services/ocr_service.py`
> * **Relevant Functions**: `extract_text_from_file()`
> * **Uncertainties**: Tesseract's accuracy on low-DPI user images has not been benchmarked.

---

## 4. Semantic Vector & Graph RAG Engine

### What it is
The dual-retrieval cognitive engine. It maps unstructured text to dense vector space and extracts explicit entity relationships to form a traversable graph.

### Why it exists
Standard vector search struggles with "multi-hop" queries (e.g., "Who manages the team that owns feature X?"). By layering a Knowledge Graph over vector search, the system can synthetically expand context before prompting the LLM.

### How it works
1. **Indexing**: 
   * `vector_service.py` lazy-loads `sentence-transformers/all-MiniLM-L6-v2`, encodes text in batches of 32 (to prevent PyTorch OOM), and upserts to Pinecone.
   * `graph_service.py` runs local `spaCy` NER. If sufficient entities are found, it hits the Groq LLM to generate `(Entity, Rel, Entity)` JSON arrays, injecting them into a `NetworkX` graph.
2. **Querying**:
   * The query is embedded, fetching the top 5 chunks via Pinecone cosine similarity.
   * `expand_query_context()` uses NER to find entities in the query, hops 1 degree in `NetworkX`, and returns associated chunks.
   * The deduplicated chunk set is sent to `groq_client.py` for final synthesis.

### Dependencies
* **Internal**: `vector_service.py`, `graph_service.py`, `groq_client.py`
* **External**: Pinecone, HuggingFace (`sentence-transformers`), Groq API, `networkx`, `spacy`.

### Risks & Common Failures
* **Risk**: High latency and LLM Rate Limiting.
* **Failure**: Groq API returns a `429 Too Many Requests`. The `graph_service.py` catches this, logs an error, and gracefully degrades to standard Vector search without crashing.

### Troubleshooting
* If answers lack specific entity relationships, check the existence of `backend/data/knowledge_graph.pkl`. If missing, the Graph RAG pipeline has been wiped by the ephemeral host.

### Future Improvements
* Upgrade `spaCy` to a fine-tuned domain-specific NER model. Implement LangChain/LlamaIndex for robust graph extraction prompt templates.

> #### Verification & Citations
> * **Accuracy Verified**: Yes.
> * **Source Files**: `D:/SemanticSearchSystem/backend/app/services/vector_service.py`, `D:/SemanticSearchSystem/backend/app/services/graph_service.py`
> * **Relevant Functions**: `add_document()`, `expand_query_context()`, `query()`
> * **Uncertainties**: Pinecone quota limits on the user's specific tier.

---

## 5. Deployment & Infrastructure

### What it is
The underlying cloud provisioning and container runtime environment.

### Why it exists
To host the application reliably and continuously on Render.com utilizing Infrastructure as Code (`render.yaml`).

### How it works
* The `Dockerfile` pulls `python:3.11-slim`, installs system binaries for OCR, and installs an explicit `cpu-only` PyTorch wheel to radically reduce image size and RAM overhead.
* It pre-downloads the HuggingFace `MiniLM` model and the `spaCy` English package during the Docker build cache layer to ensure fast runtime starts.
* Gunicorn serves the app bound to port 5000 using `--workers 1`. The `--preload` flag was intentionally removed/bypassed to allow threading to survive `fork()`.

### Dependencies
* **Internal**: `Dockerfile`, `render.yaml`, `requirements.txt`
* **External**: Render platform.

### Risks & Common Failures
* **Risk**: Running out of RAM (512MB limit) during PyTorch embedding.
* **Failure**: The Linux OOM Killer will instantly SIGKILL the container. Render will automatically reboot it, but current ingestion jobs will fail.

### Troubleshooting
* Monitor Render metrics. If memory hits 510MB consistently, lower the chunk processing batch size in `vector_service.py` from `32` to `16`.

### Future Improvements
* Upgrade to Render's paid tier to attach persistent storage disks, ensuring the SQLite local fallback databases and Job queues survive restarts.

> #### Verification & Citations
> * **Accuracy Verified**: Yes.
> * **Source Files**: `D:/SemanticSearchSystem/Dockerfile`, `D:/SemanticSearchSystem/render.yaml`
> * **Relevant Commands**: `pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu`
> * **Uncertainties**: Railway deployment viability (a legacy `railway.toml` exists but appears unused).
