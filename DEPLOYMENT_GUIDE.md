# Project Deployment Guide: Semantic Search System

This guide outlines the deployment architecture, configuration keys, database parameters, and environment requirements for deploying and maintaining the **Semantic Search System** in various environments.

---

## 📋 Table of Contents
1. [Project Overview](#1-project-overview)
2. [Prerequisites](#2-prerequisites)
3. [Repository Structure](#3-repository-structure)
4. [Environment Variables](#4-environment-variables)
5. [Local Development Setup](#5-local-development-setup)
6. [Docker Deployment](#6-docker-deployment)
7. [Render Deployment](#7-render-deployment)
8. [Frontend Deployment](#8-frontend-deployment)
9. [Database & External Services](#9-database--external-services)
10. [Production Checklist](#10-production-checklist)
11. [Troubleshooting](#11-troubleshooting)
12. [Ownership Handover Notes](#12-ownership-handover-notes)

---

## 1. Project Overview

### 1.1. Architecture Diagram
```mermaid
graph TD
    %% User Interfaces
    subgraph UI Frontend Client
        VercelUI[Static Web App: Hosted on Vercel]
        StreamlitUI[Dashboard client: Hosted on Streamlit Cloud]
    end

    %% Application API Gateway
    subgraph Backend API Gateway (Render)
        FlaskAPI[Flask App: main.py]
        ConfigContext[Config Manager: config.py]
    end

    %% Internal Processing Pipeline
    subgraph Processing Services
        OCREngine[ocr_service.py]
        VectorEngine[vector_service.py]
        GraphEngine[graph_service.py]
    end

    %% Storage Space
    subgraph Local Volume Storage
        RawStorage[Uploaded Raw Files data/]
        LocalChromaDB[(ChromaDB SQLite DB)]
        LocalPickle[(Serialized Graph knowledge_graph.pkl)]
    end

    %% SaaS Cloud APIs
    subgraph External SaaS APIs
        PineconeSaaS[(Pinecone Serverless DB Cloud)]
        GroqSaaS[Groq API Cloud: llama-3.1-8b-instant]
    end

    %% Flows
    VercelUI -->|HTTP POST| FlaskAPI
    StreamlitUI -->|HTTP POST| FlaskAPI
    FlaskAPI --> ConfigContext
    
    FlaskAPI --> OCREngine
    FlaskAPI --> VectorEngine
    FlaskAPI --> GraphEngine
    
    OCREngine -->|Writes raw files| RawStorage
    VectorEngine -->|Index SQLite| LocalChromaDB
    VectorEngine -->|Or remote upsert| PineconeSaaS
    GraphEngine -->|Read/Write Pickle| LocalPickle
    
    FlaskAPI -->|HTTPS LLM inference| GroqSaaS
```

### 1.2. High-Level Component Explanation
* **Static Frontend Client:** Decoupled HTML5/CSS3/Vanilla JS template located at [frontend/index.html](file:///d:/SemanticSearchSystem/frontend/index.html) designed to be hosted serverless (Vercel). Replaces direct rendering via local templates.
* **REST API Server:** Flask web application located at [main.py](file:///d:/SemanticSearchSystem/backend/app/main.py) which boots services, runs background daemon processing threads, and handles REST request routes.
* **Extraction Parser:** Located at [ocr_service.py](file:///d:/SemanticSearchSystem/backend/app/services/ocr_service.py) converting textual and visual formats into plain text strings.
* **Semantic Embeddings Index:** Coordinates SentenceTransformers and local ChromaDB lookup via [vector_service.py](file:///d:/SemanticSearchSystem/backend/app/services/vector_service.py).
* **Knowledge Graph Walk:** networkx directed entity graph traversal to augment prompt tokens via [graph_service.py](file:///d:/SemanticSearchSystem/backend/app/services/graph_service.py).
* **LLM Client:** Managed by [groq_client.py](file:///d:/SemanticSearchSystem/backend/app/services/groq_client.py) which queries Groq, manages exponential backoffs, and maintains query caches.

### 1.3. Request Flow
1. **Document Ingestion:** Client issues a file to `POST /upload`. Flask secures the payload on disk, registers the status as `"processing"`, spawns a daemon thread, and returns HTTP 202 immediately. The thread parses the file, segments the text, indexes the chunks in ChromaDB/Pinecone, updates the NetworkX graph, and saves state files.
2. **Context Retrieval:** Client queries the `POST /query` endpoint. Flask queries the vector database for top-similar text segments, parses term entities using spaCy, walks the NetworkX graph 1-hop away, merges/deduplicates extra context segments, and formats the unified context prompt.
3. **Inference Resolution:** The prompt is queried against Groq's model (`llama-3.1-8b-instant`), cached locally in `_llm_cache`, and returned with source metadata citations.

---

## 2. Prerequisites

### 2.1. Required Accounts
* **GitHub:** For codebase version control, deployment tracking, and CI/CD pipelines.
* **Render:** To host the containerized Flask backend API web service.
* **Vercel / Streamlit Cloud:** To host the decoupled static HTML user interface.
* **Groq Console:** To generate access credentials for the Chat Completions model.
* **Pinecone Console (Optional):** Required if transitioning storage search structures from ChromaDB SQLite to a serverless SaaS model.

### 2.2. Required Software (For Local Development)
* **Python 3.10 or 3.11**
* **Tesseract OCR CLI Engine** (required by `pytesseract` wrapper).
* **Poppler Utilities** (required by PDF image rendering engines).
* **Git CLI**

---

## 3. Repository Structure

* **`backend/`**: Logical backend process space.
  * **`backend/app/`**: Framework initialization space.
    * **`main.py`**: Web bootstrapper, background ingestion coordinator, and endpoint controller.
    * **`config.py`**: Environmental variable configuration parser.
    * **`routes.py`**: Blueprints health checks and monitoring paths.
    * **`services/`**: Ingestion, vectors, entity graph, and API client algorithms.
  * **`backend/data/`**: Runtime databases, logs, raw document storage, and graph serializations.
* **`frontend/`**: Contains static templates ([frontend/index.html](file:///d:/SemanticSearchSystem/frontend/index.html)) for decoupled static deployments.
* **`docs/`**: Documentation directories (summary logs, Handover handbooks, and guides).
* **`tests/`**: Integration test suites verifying REST routing logic.
* **`Dockerfile`**: Container image setup configuration at project root.
* **`requirements.txt`**: Declares package dependencies.

---

## 4. Environment Variables

| Variable Name | Purpose | Type | Example Value | Where Used in Code | Critical Failure Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GROQ_API_KEY` | Authenticates ChatCompletions queries sent to `api.groq.com`. | Required | `gsk_Xyz...` | [config.py](file:///d:/SemanticSearchSystem/backend/app/config.py#L14), [groq_client.py](file:///d:/SemanticSearchSystem/backend/app/services/groq_client.py#L36) | Backend queries return HTTP 500/503 errors; RAG queries crash on inference. |
| `PORT` | Sets the bind port for the Flask application server instance. | Optional | `5000` | [main.py](file:///d:/SemanticSearchSystem/backend/app/main.py#L214) | Falls back to default `5000`. |
| `FLASK_ENV` | Toggles Debug parameters (`development` enables reloaders). | Optional | `production` | [main.py](file:///d:/SemanticSearchSystem/backend/app/main.py#L215) | Falls back to `production` mode (debug configurations disabled). |
| `TESSERACT_CMD` | Overrides the search path location of the local Tesseract CLI executable. | Optional | `/usr/bin/tesseract` | [ocr_service.py](file:///d:/SemanticSearchSystem/backend/app/services/ocr_service.py#L30) | Scanned PDF page conversions and image uploads fail to extract text. |

---

## 5. Local Development Setup

### 5.1. Installation Steps
1. **Verify system dependencies exist on your host command line:**
   ```bash
   tesseract --version
   pdftoppm -v
   ```
2. **Setup directories, create virtual environment, and install modules:**
   ```bash
   git clone https://github.com/sakshamsaxena22/Semantic-Search-System.git
   cd Semantic-Search-System
   python -m venv venv
   # Windows activation:
   .\venv\Scripts\activate
   # Linux/macOS activation:
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Pre-download local model configurations and weights:**
   ```bash
   python -m spacy download en_core_web_sm
   python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
   ```
4. **Create a `.env` file at the repository root level:**
   ```env
   GROQ_API_KEY=your-groq-api-key
   FLASK_ENV=development
   PORT=5000
   ```

### 5.2. Verification & Verification Steps
```bash
# Execute unit testing suite locally (excludes slow multi-page OCR test cases)
venv\Scripts\pytest -k "not image_pdf" -v
```

---

## 6. Docker Deployment

### 6.1. Dockerfile Analysis
The [Dockerfile](file:///d:/SemanticSearchSystem/Dockerfile) uses `python:3.11-slim` as the base image. It:
1. Installs system packages: `tesseract-ocr`, `poppler-utils`, and `libgl1`.
2. Copies `requirements.txt` and runs `pip install`.
3. Pre-downloads and caches NLP/Transformer model weights:
   * Runs `spacy download en_core_web_sm`
   * Runs `SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')`
   This is critical to prevent startup timeouts in container environments where offline variables `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set in [vector_service.py](file:///d:/SemanticSearchSystem/backend/app/services/vector_service.py#L10-L11).
4. Copies project directories, creates persistent folders (`backend/data`), and sets `gunicorn` as the web worker CMD wrapper.

### 6.2. Commands
* **Build image:**
  ```bash
  docker build -t semantic-search:latest .
  ```
* **Run container (Maps volumes to keep database sqlite files preserved on host restart):**
  ```bash
  docker run -d \
    -p 5000:5000 \
    -e GROQ_API_KEY="your-groq-key" \
    -v $(pwd)/backend/data:/app/backend/data \
    --name semantic-search-container \
    semantic-search:latest
  ```

---

## 7. Render Deployment

### 7.1. Service Settings
* **Service Type:** `Web Service`
* **Runtime:** `Docker` (Render automatically builds the root `Dockerfile`)
* **Root Directory:** Keep **empty/blank** (do not set to `backend/`).
* **Dockerfile Path:** `Dockerfile`

### 7.2. Configuration Parameters
Configure the following variable key pair inside **Environment Variables**:
* `GROQ_API_KEY`: *Your actual Groq console api key string.*

### 7.3. Persistent Storage Volumes
To ensure database SQLite files (`chroma.sqlite3`) and graph pickle archives (`knowledge_graph.pkl`) survive deployment builds:
1. Navigate to **Volumes** > **Add Volume**.
2. **Mount Path:** `/app/backend/data`
3. **Name:** `backend-storage-disk`
4. **Size:** `10GB` (adjust based on document storage needs).

---

## 8. Frontend Deployment

### 8.1. Vercel Configuration
1. **Prepare static folder:** You can deploy the `frontend/` directory directly.
2. **Root Directory on Vercel:** Set to `frontend/` in settings.
3. **Build settings:** Leave as default (static HTML requires no build command).

### 8.2. Configure Target Backend API
Open **[frontend/index.html](file:///d:/SemanticSearchSystem/frontend/index.html#L308)** and set `BACKEND_URL` to your live Render endpoint:
```javascript
// Set to your actual deployed Render Web Service domain URL:
const BACKEND_URL = "https://your-backend-service.onrender.com";
```
Ensure that `CORS(app)` in [main.py](file:///d:/SemanticSearchSystem/backend/app/main.py#L36) is active to allow incoming calls from your Vercel URL domain.

---

## 9. Database & External Services

* **Local ChromaDB SQLite Persistence:** ChromaDB initializes on-disk DB stores. Ensure that the persistent disk volume is mounted to `/app/backend/data` to prevent data loss on container rebuilds.
* **NetworkX Pickles:** `knowledge_graph.pkl` is dumped at the end of every ingestion process via [graph_service.py](file:///d:/SemanticSearchSystem/backend/app/services/graph_service.py#L220) to store graph states.
* **Groq Connection Verification:**
  ```bash
  # Check if network route and credentials are correct:
  curl -X POST "https://api.groq.com/openai/v1/chat/completions" \
    -H "Authorization: Bearer YOUR_GROQ_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "test"}]}'
  ```

---

## 10. Production Checklist

* [ ] Environmental verification: Ensure `GROQ_API_KEY` is set on Render dashboard.
* [ ] Storage mount verification: Verify the persistent Render volume is mounted to `/app/backend/data`.
* [ ] CORS validation: Ensure the Render backend allows origin connections from Vercel.
* [ ] Verify container build logs: Confirm that both models (`en_core_web_sm` and `all-MiniLM-L6-v2`) are successfully built and cached during the image compilation stage.

---

## 11. Troubleshooting

### 11.1. Connect Timeout Errors in Tests
* **Symptoms:** Pytest returns `MaxRetryError` or `ConnectionTimeout` on `/upload`.
* **Root Cause:** The tests ran before the backend server finished loading SentenceTransformers or ChromaDB indexes into memory.
* **Diagnostic Steps:** Check server startup logs; verify if it reached the `DEBUG 6: Central state ready` checkpoint.
* **Fix:** Wait 30 seconds after server startup before running the test suite.

### 11.2. SQLite Database Lock Errors
* **Symptoms:** Errors indicating `database is locked` in `vector_service.log`.
* **Root Cause:** Multiple background processes/workers attempting write operations to ChromaDB simultaneously.
* **Fix:** Set Gunicorn workers to exactly 1 (`--workers 1`) to ensure thread-safe SQLite operations.

### 11.3. 429 Rate Limits on Groq
* **Symptoms:** Logs show `Groq call failed after 6 retries`.
* **Root Cause:** The API key has hit the limits of the free tier.
* **Fix:** Ensure query caching (`_llm_cache` in [groq_client.py](file:///d:/SemanticSearchSystem/backend/app/services/groq_client.py)) is active for identical queries. Upgrade Groq account tier if needed.

---

## 12. Ownership Handover Notes

### 12.1. Dependency Updates
To upgrade python packages, update `requirements.txt` and rebuild the container. Remember to run a model pre-caching command (`RUN python -c ...`) in the `Dockerfile` for any new models added.

### 12.2. Secret Rotation
1. Generate a new API key in the Groq Console.
2. Update the `GROQ_API_KEY` environment variable in the Render Dashboard settings.
3. Restart the web service to load the new configuration.

### 12.3. Disaster Recovery
If the local database becomes corrupted:
1. Stop the Render service.
2. Delete the contents of the `/app/backend/data/chroma_db/` directory and remove `knowledge_graph.pkl`.
3. Restart the service to initialize a fresh, empty vector index and knowledge graph.
4. Re-upload your raw documents via the frontend user interface.
