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
│           HTML5 + JavaScript (upload.html)                  │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP Requests
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 Flask Application Layer                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  main.py - Application Bootstrap & Route Handlers    │ │
│  │  - GET  /           → Serve upload.html              │ │
│  │  - POST /upload     → Handle file uploads             │ │
│  │  - POST /query      → Process semantic searches       │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  routes.py - Blueprint API Routes                     │ │
│  │  - POST /api/query  → Direct LLM queries              │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌──────────┐  ┌──────────┐
    │   OCR   │  │  Vector  │  │  Groq    │
    │ Service │  │  Service │  │  Client  │
    └─────────┘  └──────────┘  └──────────┘
         │             │             │
         ▼             ▼             ▼
    ┌─────────┐  ┌──────────┐  ┌──────────┐
    │ PyMuPDF │  │In-Memory │  │ Groq API │
    │Tesseract│  │Vector DB │  │(LLaMA-3) │
    │python-  │  │          │  │          │
    │docx     │  │          │  │          │
    └─────────┘  └──────────┘  └──────────┘
```

### Component Breakdown:

#### 1. **Frontend Layer**
- **upload.html**: Single-page application
  - File upload functionality (multi-file support, up to 75 files)
  - Query input interface
  - Response display with citations

#### 2. **Application Layer (Flask)**
- **main.py**: Core Flask application
  - Initializes Flask app with CORS support
  - Manages upload folder and file size limits (16MB max)
  - Coordinates between services
  - Error handling and logging

- **routes.py**: Blueprint for additional API routes
  - RESTful API endpoint for direct LLM queries

- **config.py**: Configuration management
  - Loads environment variables (GROQ_API_KEY)
  - Data directory configuration

#### 3. **Service Layer**

**OCR Service** (`ocr_service.py`)
- Multi-format text extraction
- File type detection via extension
- Error handling for unsupported formats

**Vector Service** (`vector_service.py`)
- In-memory vector database (demo implementation)
- Document chunk storage with metadata
- Query interface for retrieving relevant chunks
- Note: Production use should integrate ChromaDB or similar

**Groq Client** (`groq_client.py`)
- HTTP communication with Groq API
- LLaMA-3 8B model integration
- Authentication via API key
- Error handling for API failures

**Groq Service** (`groq_service.py`)
- Wrapper around Groq client
- Text chunking for large prompts
- Batch processing capability

#### 4. **Storage Layer**
- **backend/data/**: Uploaded files storage
- **In-Memory Vector Store**: Document chunks and metadata

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
- **Trigger**: `python -m backend.app.main` or `python backend/app/main.py`
- **Port**: Default Flask port 5000
- **Function**: 
  - Initializes Flask application
  - Loads configuration and services
  - Starts the web server

### 2. **Frontend Entry Point**
- **URL**: `http://localhost:5000/`
- **File Served**: `backend/app/templates/upload.html`
- **Capabilities**:
  - Upload files
  - Query documents
  - View AI-generated answers

---

## 🔌 API Endpoints

### Frontend Routes

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| GET | `/` | Serve upload UI | - | HTML page |
| POST | `/upload` | Upload document | File (multipart) | `{status, file}` |
| POST | `/query` | Query documents | `{query: string}` | `{answer, citations}` |

### API Blueprint Routes

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| POST | `/api/query` | Direct LLM query | `{query: string}` | `{answer: string}` |

### Request/Response Examples

**Upload Document**
```bash
curl -X POST -F "file=@document.pdf" http://localhost:5000/upload
```

Response:
```json
{
  "status": "success",
  "file": "document.pdf"
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
  "citations": [{"source": "document.pdf", "chunk": 0}]
}
```

---

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.10+
- pip package manager
- Tesseract OCR (for image text extraction)
- Poppler utilities (for PDF processing)
- Groq API key

### Installation Steps

1. **Clone Repository**
```bash
git clone https://github.com/sakshamsaxena22/Semantic-Search-System.git
cd Semantic-Search-System
```

2. **Create Virtual Environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
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
```bash
cp .env.example .env  # If available, or create .env
# Add your Groq API key
echo "GROQ_API_KEY=your_api_key_here" > .env
```

Get your Groq API key from: https://console.groq.com/

6. **Run Application**
```bash
python backend/app/main.py
```

7. **Access Application**
Open browser and navigate to: `http://localhost:5000`

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

**Python Example:**
```python
import requests

# Upload document
with open('document.pdf', 'rb') as f:
    files = {'file': f}
    response = requests.post('http://localhost:5000/upload', files=files)
    print(response.json())

# Query document
query_data = {'query': 'What is the summary?'}
response = requests.post('http://localhost:5000/query', json=query_data)
print(response.json())
```

**JavaScript Example:**
```javascript
// Upload file
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch('/upload', {
  method: 'POST',
  body: formData
}).then(res => res.json()).then(data => console.log(data));

// Query documents
fetch('/query', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({query: 'Your question here'})
}).then(res => res.json()).then(data => console.log(data.answer));
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
```bash
docker build -t semantic-search:latest ./backend
```

### Run Docker Container
```bash
docker run -p 5000:5000 \
  -e GROQ_API_KEY=your_api_key \
  -v $(pwd)/backend/data:/app/backend/data \
  semantic-search:latest
```

---

## 🔐 Security Considerations

- **API Key Management**: Store GROQ_API_KEY securely in environment variables
- **File Upload Limits**: Default 16MB max file size
- **CORS Configuration**: Configure allowed origins in production
- **Input Validation**: All file types and queries are validated
- **Error Handling**: Sensitive information is not exposed in error messages

---

## 📝 Notes

- The current Vector Store is in-memory (demo implementation)
- For production, integrate ChromaDB or Pinecone for persistent storage
- Chunking strategy (500 chars) can be optimized based on content type
- LLM model can be switched in groq_client.py
- Consider implementing authentication for production use

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

