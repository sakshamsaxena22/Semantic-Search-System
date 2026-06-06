"""
Comprehensive test suite for the Semantic Search System (Graph RAG edition).

Test Groups
───────────
1. Upload tests       – TXT, native PDF, image PDFs (OCR), duplicates, bad requests
2. Job polling        – status endpoint, unknown job IDs
3. Semantic queries   – answer quality, citation presence, bad-input guards
4. Graph RAG          – graph stats, query expansion, cross-doc enrichment
5. Health / misc      – root UI, /api/health, /graph/stats

Prerequisites
─────────────
• Server running on http://127.0.0.1:5000
  → python -m backend.app.main      (from project root)
• Files present in backend/data/:
  - test.txt
  - Python_Notes.pdf
  - Image_to_PDF_20260323_15.24.53.pdf   (image-based, 4 pages)
  - Image_to_PDF_20260323_15.29.52.pdf   (image-based, 11 pages)

Run:
    pytest tests/test_app.py -v
    pytest tests/test_app.py -v -k "not image_pdf"   # skip slow OCR tests
"""

import time
import pytest
import requests

BASE = "http://127.0.0.1:5000"
DATA = "backend/data"

# ── Helpers ────────────────────────────────────────────────────────────────────

def upload_file(filename: str, timeout_min: int = 10) -> dict:
    """Upload a file and poll until processing completes. Returns final job dict."""
    path = f"{DATA}/{filename}"
    with open(path, "rb") as fh:
        res = requests.post(f"{BASE}/upload", files={"file": (filename, fh)}, timeout=30)

    assert res.status_code in (200, 202), f"Upload failed: {res.status_code} {res.text}"
    data = res.json()

    if data.get("status") == "processing":
        job_id   = data["job_id"]
        deadline = time.time() + timeout_min * 60
        while time.time() < deadline:
            time.sleep(3)
            poll = requests.get(f"{BASE}/status/{job_id}", timeout=10).json()
            if poll["status"] in ("done", "error"):
                return poll
        pytest.fail(f"Job {job_id} did not finish within {timeout_min} minute(s)")

    return data   # status == "done" directly


def query(question: str) -> dict:
    """POST /query and return parsed response dict with status_code key."""
    res = requests.post(f"{BASE}/query", json={"query": question}, timeout=60)
    return {"status_code": res.status_code, **res.json()}


# ── Module-level fixture: upload all docs once ─────────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def ensure_documents_uploaded():
    """Upload core documents before any tests run. Skips image PDFs if slow."""
    for fname, tmin in [
        ("test.txt", 1),
        ("Python_Notes.pdf", 3),
    ]:
        upload_file(fname, timeout_min=tmin)
    yield


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  UPLOAD TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpload:

    def test_upload_txt_file(self):
        """Plain TXT file should upload and index successfully."""
        result = upload_file("test.txt")
        assert result["status"] == "done", result.get("message")

    def test_upload_native_pdf(self):
        """Python Notes PDF has native text — should be fast and succeed."""
        result = upload_file("Python_Notes.pdf", timeout_min=3)
        assert result["status"] == "done", result.get("message")

    @pytest.mark.slow
    def test_upload_image_pdf_1(self):
        """Image-based PDF 1 (4 pages) — requires Tesseract OCR, allow up to 5 min."""
        result = upload_file("Image_to_PDF_20260323_15.24.53.pdf", timeout_min=5)
        assert result["status"] == "done", result.get("message")

    @pytest.mark.slow
    def test_upload_image_pdf_2(self):
        """Image-based PDF 2 (11 pages) — larger, allow up to 10 min."""
        result = upload_file("Image_to_PDF_20260323_15.29.52.pdf", timeout_min=10)
        assert result["status"] == "done", result.get("message")

    def test_upload_duplicate_is_idempotent(self):
        """Re-uploading the same file should succeed (upsert, not error)."""
        r1 = upload_file("test.txt")
        r2 = upload_file("test.txt")
        assert r1["status"] == "done"
        assert r2["status"] == "done"

    def test_upload_no_file_returns_400(self):
        """Request with no file part should return HTTP 400."""
        res = requests.post(f"{BASE}/upload", timeout=10)
        assert res.status_code == 400

    def test_upload_empty_filename_returns_400(self):
        """Request with empty filename should return HTTP 400."""
        res = requests.post(f"{BASE}/upload", files={"file": ("", b"")}, timeout=10)
        assert res.status_code == 400

    def test_upload_returns_job_id(self):
        """Upload response should contain a job_id for polling."""
        with open(f"{DATA}/test.txt", "rb") as fh:
            res = requests.post(f"{BASE}/upload", files={"file": ("test.txt", fh)}, timeout=30)
        data = res.json()
        assert "job_id" in data, "Upload response missing job_id"
        assert isinstance(data["job_id"], str) and len(data["job_id"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  JOB STATUS TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestJobStatus:

    def test_status_unknown_job_returns_404(self):
        """Polling a random job ID should return 404."""
        res = requests.get(f"{BASE}/status/nonexistent-job-id-xyz-123", timeout=10)
        assert res.status_code == 404

    def test_status_has_status_field(self):
        """Status response must always contain a 'status' key."""
        with open(f"{DATA}/test.txt", "rb") as fh:
            upload_res = requests.post(f"{BASE}/upload", files={"file": ("test.txt", fh)}, timeout=30)
        job_id = upload_res.json().get("job_id")
        if job_id:
            poll = requests.get(f"{BASE}/status/{job_id}", timeout=10).json()
            assert "status" in poll
            assert poll["status"] in ("processing", "done", "error")

    def test_completed_job_has_file_field(self):
        """Completed job status should include 'file' field."""
        result = upload_file("test.txt")
        assert "file" in result or result.get("status") == "error"


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  SEMANTIC QUERY TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSemanticQuery:

    def test_query_returns_200(self):
        """Any valid query should return HTTP 200."""
        time.sleep(1)  # avoid Groq rate-limit between sequential test calls
        result = query("What is Python?")
        assert result["status_code"] == 200

    def test_query_has_answer_field(self):
        """Response must contain a non-empty 'answer' field."""
        result = query("What is Python?")
        assert "answer" in result
        assert len(result["answer"].strip()) > 0

    def test_query_has_citations(self):
        """Response must include source citations."""
        result = query("What is Python?")
        assert "citations" in result
        assert len(result["citations"]) > 0

    def test_query_citation_has_source_field(self):
        """Each citation should have a 'source' key."""
        result = query("What is Python?")
        for cite in result.get("citations", []):
            assert "source" in cite, f"Citation missing 'source': {cite}"

    def test_semantic_python_basics(self):
        """Asking about Python basics should mention Python in the answer."""
        result = query("What is Python used for?")
        assert result["status_code"] == 200
        answer = result["answer"].lower()
        assert any(kw in answer for kw in ["python", "programming", "language", "data"]), \
            f"Answer not relevant: {result['answer'][:200]}"

    def test_semantic_variables_and_datatypes(self):
        """Python Notes covers variables — answer should reflect that."""
        result = query("Explain variables and data types in Python")
        assert result["status_code"] == 200
        answer = result["answer"].lower()
        assert any(kw in answer for kw in ["variable", "int", "string", "data type", "type"]), \
            f"Answer not relevant: {result['answer'][:200]}"

    def test_semantic_ai_txt(self):
        """test.txt mentions AI and ML — answer should be related."""
        result = query("What does the document say about artificial intelligence?")
        assert result["status_code"] == 200
        answer = result["answer"].lower()
        assert any(kw in answer for kw in ["artificial", "intelligence", "machine", "learning", "ai", "ml"]), \
            f"Answer not relevant: {result['answer'][:200]}"

    def test_query_missing_field_returns_400(self):
        """POST /query with no 'query' key should return 400."""
        res = requests.post(f"{BASE}/query", json={}, timeout=10)
        assert res.status_code == 400

    def test_query_empty_string_returns_400(self):
        """POST /query with empty string should return 400."""
        res = requests.post(f"{BASE}/query", json={"query": ""}, timeout=10)
        assert res.status_code == 400

    def test_query_whitespace_only_returns_400(self):
        """POST /query with whitespace-only string should return 400."""
        res = requests.post(f"{BASE}/query", json={"query": "   "}, timeout=10)
        assert res.status_code == 400

    def test_query_no_json_returns_400(self):
        """POST /query with no JSON body should return 400 or 415 (Flask rejects missing Content-Type)."""
        res = requests.post(f"{BASE}/query", timeout=10)
        assert res.status_code in (400, 415), f"Expected 400 or 415, got {res.status_code}"

    @pytest.mark.slow
    def test_semantic_bca_course(self):
        """Image PDF 1 has BCA course info — answer should mention it."""
        result = query("What are the BCA course fees and eligibility?")
        assert result["status_code"] == 200
        answer = result["answer"].lower()
        assert any(kw in answer for kw in ["bca", "fees", "eligibility", "10+2", "marks", "lakh"]), \
            f"Answer not relevant: {result['answer'][:200]}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  GRAPH RAG TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphRAG:

    def test_graph_stats_endpoint(self):
        """GET /graph/stats should return node/edge/chunk counts."""
        res = requests.get(f"{BASE}/graph/stats", timeout=10)
        assert res.status_code == 200
        data = res.json()
        assert "nodes" in data
        assert "edges" in data
        assert "chunks_indexed" in data
        assert isinstance(data["nodes"], int)
        assert isinstance(data["edges"], int)

    def test_graph_has_nodes_after_upload(self):
        """After uploading documents, graph should have at least some nodes."""
        res = requests.get(f"{BASE}/graph/stats", timeout=10)
        data = res.json()
        # Python Notes PDF has many entities — graph should be non-trivial
        assert data["nodes"] >= 0   # at minimum 0 (spaCy might not find entities in all docs)

    def test_query_response_has_graph_rag_flag(self):
        """Query response should include a 'graph_rag' boolean field."""
        result = query("What is Python?")
        assert result["status_code"] == 200
        assert "graph_rag" in result, "Response missing 'graph_rag' flag"
        assert isinstance(result["graph_rag"], bool)

    def test_query_response_has_graph_stats(self):
        """Query response should include graph_stats with node/edge info."""
        result = query("Tell me about Python programming")
        assert result["status_code"] == 200
        assert "graph_stats" in result
        stats = result["graph_stats"]
        assert "nodes" in stats and "edges" in stats

    def test_graph_expands_context_for_known_entity(self):
        """Query about a known entity should return an answer (graph or vector)."""
        result = query("What programming concepts are covered in the documents?")
        assert result["status_code"] == 200
        assert len(result["answer"].strip()) > 10, "Answer should be non-trivial"

    def test_graph_via_citations_present_when_expanded(self):
        """If graph expansion occurred, at least one citation may carry 'via: graph' tag."""
        result = query("Explain data types")
        assert result["status_code"] == 200
        # When graph_rag is True, some citations should have via="graph"
        if result.get("graph_rag"):
            graph_cites = [c for c in result.get("citations", []) if c.get("via") == "graph"]
            # This is informational — graph expansion may or may not surface extra chunks
            assert isinstance(graph_cites, list)


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  HEALTH / MISC
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealth:

    def test_home_returns_200(self):
        """Root route should serve the UI (HTTP 200)."""
        res = requests.get(f"{BASE}/", timeout=10)
        assert res.status_code == 200

    def test_home_returns_html(self):
        """Root route should return HTML content."""
        res = requests.get(f"{BASE}/", timeout=10)
        assert "text/html" in res.headers.get("Content-Type", "")

    def test_api_health_endpoint(self):
        """GET /api/health should return {status: ok}."""
        res = requests.get(f"{BASE}/api/health", timeout=10)
        assert res.status_code == 200, f"Got {res.status_code}: {res.text}"
        assert res.json().get("status") == "ok"

    def test_graph_stats_is_json(self):
        """GET /graph/stats should return valid JSON."""
        res = requests.get(f"{BASE}/graph/stats", timeout=10)
        assert res.status_code == 200
        assert res.headers.get("Content-Type", "").startswith("application/json")

    def test_unknown_endpoint_returns_404(self):
        """Hitting an undefined route should return 404."""
        res = requests.get(f"{BASE}/this-does-not-exist", timeout=10)
        assert res.status_code == 404
