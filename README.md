# Semantic Search System

## 📋 Table of Contents
- [Project Overview](#project-overview)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Entry Points](#entry-points)
- [API Endpoints](#api-endpoints)
- [Setup & Installation](#setup--installation)
- [Usage Guide](#usage-guide)
- [Technologies & Dependencies](#technologies--dependencies)

---

## 🎯 Project Overview

**Semantic Search System** is a document intelligence platform that enables users to upload various document formats (PDF, images, Word docs, text files), extract their content using OCR and text extraction, store them in a vector database, and intelligently query them using semantic search with AI-powered responses.

### Key Features:
- **Multi-format Support**: PDF, images (JPG, PNG, BMP, TIFF, HEIC), DOCX, and TXT files
- **OCR Capabilities**: Extract text from scanned documents and images using Tesseract
- **Vector Storage**: Store document chunks for efficient semantic search
- **AI-Powered Responses**: Integration with Groq's LLaMA-3 model for intelligent query answering
- **Web Interface**: Simple HTML UI for file uploads and document querying
- **RESTful API**: Backend API for programmatic access
- **CORS Support**: Enable cross-origin requests for frontend integration

---

## 🔄 How It Works

### Workflow Overview:

1. **Document Upload**
   - User uploads a document (PDF, image, DOCX, or TXT)
   - Flask backend receives the file and validates it
   - File is saved to the `backend/data` directory

2. **Text Extraction (OCR Service)**
   - **PDF Files**: PyMuPDF (fitz) extracts text from PDF pages
   - **Images**: Tesseract OCR converts image content to text
   - **Word Documents**: python-docx parses DOCX structure and extracts paragraphs
   - **Text Files**: Direct file reading with UTF-8 encoding

3. **Chunking & Vector Storage**
   - Extracted text is split into 500-character chunks (configurable)
   - Chunks are stored in the Vector Store with metadata
   - Each chunk maintains reference to source document

4. **Query Processing**
   - User submits a semantic search query
   - Vector Store retrieves all relevant document chunks
   - Retrieved context is formatted into a prompt

5. **LLM Response Generation**
   - Formatted prompt is sent to Groq API (LLaMA-3 8B model)
   - Model generates contextual answer based on document content
   - Response is returned to the frontend with citations

---

## 🏗️ Architecture

### System Architecture Diagram:

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Web UI)                         │
│           HTML5 + JavaScript (index.html)                   │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP Requests (Parallel Uploads)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 Flask Application Layer (main.py)           │
│  - GET  /            → Serve index.html                     │
│  - POST /upload      → Enqueue job & return 202             │
│  - GET  /status/<id> → Poll background job state            │
│  - POST /query       → Hybrid Vector + Graph Search         │
│                                                             │
│  ┌──────────────────┐               ┌────────────────────┐  │
│  │  Work Queue      │               │  Persistent Jobs   │  │
│  │  (queue.Queue)   │               │  (.jobs.json)      │  │
│  └────────┬─────────┘               └────────────────────┘  │
│           │ (Sequential Processing Thread)                  │
│           ▼                                                 │
│  ┌──────────────────┐                                       │
│  │  OCR Service     │ (150 DPI Tesseract / PyMuPDF)         │
│  └────────┬─────────┘                                       │
│           │ (Deletes raw file after extraction)             │
│           ▼                                                 │
│  ┌──────────────────┐                                       │
│  │  Vector Service  │ (Streamed Encoding, 32 Chunk Batches) │
│  └──────────────────┘                                       │
└───────────────────┬─────────────────────────────────────────┘
                    │
      ┌─────────────┴─────────────┐
      ▼                           ▼
┌───────────┐               ┌───────────┐
│ Pinecone  │               │ Groq LLM  │
│ Vector DB │               │ API Gateway│
│ (ChromaDB │               │ (Llama 3  │
│ Fallback) │               │ Caching)  │
└───────────┘               └───────────┘
```

### Component Breakdown:

#### 1. **Frontend Layer**
- **index.html**: Decoupled browser client UI.
  - Fast, parallel file uploads (up to 75 files).
  - Real-time job status dashboard showing ⏳ Queued, 🔄 Processing, ✅ Done, and ❌ Failed status icons.
  - Multi-file querying and citation links.

#### 2. **Application Layer (Flask)**
- **main.py**: Core Flask application.
  - Manages background sequential queue (`queue.Queue`) and persistent job store (`.jobs.json`).
  - Implements API endpoints with CORS support.
  - Cleans up uploaded raw files immediately after extraction to save server disk space.

- **routes.py**: Blueprint for additional API endpoints.

- **config.py**: Environment variable configuration.

#### 3. **Service Layer**
- **OCR Service** (`ocr_service.py`): Multi-format text extraction rendering scanned PDF pages at 150 DPI to optimize memory footprint and speed.
- **Vector Service** (`vector_service.py`): Primary Pinecone client with local ChromaDB SQLite fallback. Uses 32-chunk batch streamed encoding to prevent memory spikes.
- **Groq Client** (`groq_client.py`): Groq API gateway with backoff strategy, response caching (max 200 items), and retry capability.
- **Graph Service** (`graph_service.py`): NetworkX graph expansion engine walking 1-hop relationships from `knowledge_graph.pkl` at query time.

#### 4. **Storage Layer**
- **Pinecone Vector Database**: Cloud vector index (384 dimensions).
- **ChromaDB**: Local SQLite vector database (fallback when Pinecone credentials are absent).
- **Disk Persistence**: `.jobs.json` (status tracker) and `knowledge_graph.pkl` (relationship graph).

---

## 📁 Project Structure

```
Semantic-Search-System/
├── README.md                          # Project documentation
├── requirements.txt                   # Python dependencies
├── __init__.py                        # Package initialization
│
├── backend/
│   ├── __init__.py
│   ├── Dockerfile                     # Docker configuration
│   ├── requirements.txt               # Backend dependencies (same as root)
│   │
│   ├── data/                          # Uploaded documents storage
│   │   └── .gitkeep
│   │
│   └── app/
│       ├── __init__.py
│       ├── main.py                    # Flask application entry point
│       ├── config.py                  # Configuration management
│       ├── routes.py                  # API blueprint routes
│       │
│       ├── core/                      # Core functionality (expandable)
│       │   └── __init__.py
│       │
│       ├── services/                  # Business logic services
│       │   ├── __init__.py
│       │   ├── ocr_service.py        # Text extraction from documents
│       │   ├── vector_service.py     # Vector database operations
│       │   ├── groq_client.py        # Groq API client
│       │   └── groq_service.py       # LLM service wrapper
│       │
│       └── templates/                 # HTML templates
│           └── upload.html            # Frontend UI
│
└── .github/                           # GitHub workflows (CI/CD)
```

---

## 🚀 Entry Points

### 1. **Application Entry Point**
- **File**: `backend/app/main.py`
- **Trigger**: `python backend/app/main.py` or `python -m backend.app.main`
- **Port**: Default Flask port 5000
- **Function**: 
  - Initializes Flask application
  - Launches background sequential job queue daemon thread
  - Restores existing jobs from disk
  - Serves static front-end and APIs

### 2. **Frontend Entry Point**
- **URL**: `http://localhost:5000/`
- **File Served**: `frontend/index.html` (via Flask root route)
- **Capabilities**:
  - Parallel fire-and-forget uploads
  - Real-time status polling for queued jobs
  - Search query submission and Graph RAG citation viewer

---

## 🔌 API Endpoints

### Frontend Routes

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| GET | `/` | Serve index.html | - | HTML page |
| POST | `/upload` | Enqueue document | File (multipart) | `{"status": "processing", "job_id": "...", "file": "..."}` |
| GET | `/status/<job_id>` | Poll job progress | - | `{"status": "done"\|"processing"\|"error", "file": "...", "message": "..."}` |
| POST | `/query` | Query documents | `{"query": string}` | `{"answer", "citations", "graph_rag", "graph_stats"}` |
| GET | `/graph/stats` | Retrieve Graph status | - | `{"nodes", "edges", "chunks_indexed"}` |

### API Blueprint Routes

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| POST | `/api/query` | Direct LLM query | `{"query": string}` | `{"answer": string}` |

### Request/Response Examples

**Upload Document**
```bash
curl -X POST -F "file=@document.pdf" http://localhost:5000/upload
```

Response (HTTP 202):
```json
{
  "status": "processing",
  "job_id": "8b9ff6a2-11c0-432d-8ab1-2f31a293f9c2",
  "file": "document.pdf"
}
```

**Check Upload/Processing Status**
```bash
curl http://localhost:5000/status/8b9ff6a2-11c0-432d-8ab1-2f31a293f9c2
```

Response:
```json
{
  "status": "done",
  "file": "document.pdf",
  "message": "Indexed 15 chunks."
}
```

**Query Documents**
```bash
curl -X POST http://localhost:5000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the main topic?"}'
```

Response:
```json
{
  "answer": "The main topic is...",
  "citations": [{"source": "document.pdf", "chunk": 0}],
  "graph_rag": true,
  "graph_stats": {"nodes": 12, "edges": 25, "chunks_indexed": 15}
}
```

---

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.10+
- Tesseract OCR (for image text extraction)
- Poppler utilities (for PDF processing)
- Groq API key (and optionally Pinecone API key & Index Name)

### Installation Steps

1. **Clone Repository**
```bash
git clone https://github.com/sakshamsaxena22/Semantic-Search-System.git
cd Semantic-Search-System
```

2. **Create Virtual Environment**
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

3. **Install Dependencies**
Install PyTorch CPU-only first to prevent CUDA package bloat (~1.5GB savings):
```bash
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

4. **Install System Dependencies**

**Ubuntu/Debian:**
```bash
sudo apt-get install -y poppler-utils tesseract-ocr
```

**macOS:**
```bash
brew install poppler tesseract
```

**Windows:**
- Download Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
- Download Poppler: http://blog.alivate.com.au/poppler-windows/

5. **Configure Environment Variables**
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_key_here
PINECONE_API_KEY=your_pinecone_key_here
PINECONE_INDEX_NAME=semantic-search-index
```

6. **Run Application**
```bash
python backend/app/main.py
```

7. **Access Application**
Open your browser and navigate to: `http://localhost:5000`

---

## 💻 Usage Guide

### Web Interface Usage

1. **Upload Documents**
   - Click "Choose Files" or drag-and-drop
   - Select up to 75 files
   - Supported formats: PDF, JPG, PNG, DOCX, TXT
   - Click "Upload Files" button
   - Wait for confirmation

2. **Query Documents**
   - Enter your question in the query box
   - Click "Submit Query"
   - View AI-generated answer below
   - Check citations for source information

### Programmatic API Usage

**Python Example (with status polling):**
```python
import time
import requests

# 1. Start Upload
with open('document.pdf', 'rb') as f:
    res = requests.post('http://localhost:5000/upload', files={'file': f})
    job = res.json()
    job_id = job['job_id']
    print(f"Uploaded! Job ID: {job_id}")

# 2. Poll Status
while True:
    res = requests.get(f'http://localhost:5000/status/{job_id}')
    status_data = res.json()
    print(f"Status: {status_data['status']} - {status_data.get('message', '')}")
    if status_data['status'] in ['done', 'error']:
        break
    time.sleep(2)

# 3. Query the Indexed Content
query_data = {'query': 'What is the summary?'}
res = requests.post('http://localhost:5000/query', json=query_data)
print("Answer:", res.json()['answer'])
```

**JavaScript Example (with status polling):**
```javascript
// 1. Upload file
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const uploadRes = await fetch('/upload', { method: 'POST', body: formData });
const uploadData = await uploadRes.json();
const jobId = uploadData.job_id;

// 2. Poll Status
const pollInterval = setInterval(async () => {
  const statusRes = await fetch(`/status/${jobId}`);
  const statusData = await statusRes.json();
  console.log("Status:", statusData.status);
  
  if (statusData.status === 'done' || statusData.status === 'error') {
    clearInterval(pollInterval);
    console.log("Finished:", statusData.message);
  }
}, 3000);
```

---

## 📦 Technologies & Dependencies

### Core Framework
- **Flask 3.1.1**: Lightweight Python web framework
- **FastAPI 0.115.9**: Modern async web framework support
- **Uvicorn 0.34.2**: ASGI server

### Document Processing
- **PyMuPDF 1.25.5**: PDF text extraction
- **Tesseract OCR 0.3.13**: Optical character recognition
- **Pillow 11.2.1**: Image processing
- **python-docx**: Word document (.docx) parsing

### AI & Embeddings
- **LangChain 0.3.25**: LLM orchestration framework
- **Sentence Transformers 4.1.0**: Text embeddings
- **Transformers 4.51.3**: HuggingFace model support
- **PyTorch 2.7.0**: Deep learning framework

### Vector Database
- **ChromaDB 1.0.9**: Vector database (optional, currently using in-memory)
- **SQLAlchemy 2.0.41**: Database ORM

### API Integration
- **Requests 2.32.3**: HTTP client
- **HTTPX 0.28.1**: Async HTTP client

### Utilities
- **python-dotenv 1.1.0**: Environment variable management
- **Pydantic 2.11.4**: Data validation
- **NumPy 2.2.6**: Numerical computing
- **SciPy 1.15.3**: Scientific computing

### Development Tools
- **Flask-CORS 6.0.0**: Cross-Origin Resource Sharing
- **python-dateutil 2.9.0**: Date utilities

---

## 🐳 Docker Deployment

### Build Docker Image
Run from the project root directory:
```bash
docker build -t semantic-search:latest .
```

### Run Docker Container
```bash
docker run -p 5000:5000 \
  -e GROQ_API_KEY=your_groq_key \
  -e PINECONE_API_KEY=your_pinecone_key \
  -e PINECONE_INDEX_NAME=semantic-search-index \
  -v $(pwd)/backend/data:/app/backend/data \
  semantic-search:latest
```

---

## 🔐 Security Considerations

- **API Key Management**: Store GROQ_API_KEY and PINECONE_API_KEY securely in environment variables.
- **File Upload Limits**: Managed on both backend (max 32MB) and frontend.
- **CORS Configuration**: CORS support is configured to allow decoupled frontend communication.
- **Input Validation**: File uploads and search queries are strictly validated.

---

## 📝 Notes

- **Vector Database**: Connects to Pinecone for persistent cloud storage. Falls back automatically to local ChromaDB SQLite storage if Pinecone keys are missing.
- **Graph RAG Ingestion**: Graph construction is bypassed during document ingestion to preserve memory and speed up uploading. At query time, entity connections are walked using pre-loaded relationships if available.
- **Memory Optimization**: Employs lazy model loading, CPU-only PyTorch, 150 DPI OCR page rendering, and 32-chunk batch streaming to operate smoothly on low-RAM environments (e.g. Render's 512MB free tier).

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

---

## 📄 License

This project is open source and available under the MIT License.

---

## 📞 Support

For issues, questions, or suggestions, please open an issue in the GitHub repository.

