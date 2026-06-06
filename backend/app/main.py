"""
Main application file for the Semantic Search System.
Run from the project root: python -m backend.app.main
Or directly:               python backend/app/main.py
"""
import os
import sys
import uuid
import logging
import threading
import json
import gc
import queue
import time
import traceback
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename

# ── Ensure the project root is on sys.path so imports work whether the app
#    is launched as a module or as a plain script. ──────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.app.services.ocr_service import extract_text_from_file
from backend.app.services.vector_service import VectorStore
from backend.app.services.groq_client import groq_call_llm
from backend.app.services.graph_service import KnowledgeGraph

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR      = _ROOT
APP_DIR       = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "backend", "data")

# ── App setup ──────────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "frontend"))
app.config["UPLOAD_FOLDER"]      = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024   # 32 MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ── Shared state ─────────────────────────────────────────────────────────────────────────
if os.environ.get("PINECONE_API_KEY") and os.environ.get("PINECONE_INDEX_NAME"):
    logging.info("Startup check: Pinecone env vars DETECTED. VectorStore will use Pinecone.")
else:
    logging.warning("Startup check: Pinecone env vars MISSING. VectorStore will fallback to ChromaDB.")

vector_store    = VectorStore()
knowledge_graph = KnowledgeGraph()
logging.info("App initialized: VectorStore + KnowledgeGraph ready.")

# ── Persistent job tracking (survives worker restarts) ─────────────────────────
_JOBS_FILE = os.path.join(UPLOAD_FOLDER, ".jobs.json")
_jobs_lock = threading.RLock()

def _load_jobs() -> dict:
    """Load jobs from disk. Returns empty dict on any failure."""
    with _jobs_lock:
        try:
            if os.path.isfile(_JOBS_FILE):
                with open(_JOBS_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

def _save_jobs(jobs: dict):
    """Persist jobs dict to disk."""
    with _jobs_lock:
        try:
            with open(_JOBS_FILE, "w") as f:
                json.dump(jobs, f)
        except Exception as e:
            logging.error("Failed to persist jobs: %s", e)

# Reset stuck jobs on startup
with _jobs_lock:
    _initial_jobs = _load_jobs()
    _changed = False
    for j_id, j_data in _initial_jobs.items():
        if j_data.get("status") == "processing":
            j_data["status"] = "error"
            j_data["message"] = "Server restarted while processing. Please upload again."
            _changed = True
    if _changed:
        _save_jobs(_initial_jobs)

def _set_job(job_id: str, status: str, filename: str, message: str = ""):
    """Update a single job and persist to disk."""
    with _jobs_lock:
        jobs = _load_jobs()
        jobs[job_id] = {"status": status, "file": filename, "message": message}
        # Keep only the last 200 jobs to prevent unbounded growth
        if len(jobs) > 200:
            sorted_ids = sorted(jobs.keys())
            for old_id in sorted_ids[:-200]:
                del jobs[old_id]
        _save_jobs(jobs)

def _get_job(job_id: str) -> dict | None:
    """Retrieve a single job."""
    with _jobs_lock:
        return _load_jobs().get(job_id)

# ── Sequential processing queue (one file at a time = stable RAM) ──────────────
_work_queue: queue.Queue = queue.Queue()


# ── Error handlers ─────────────────────────────────────────────────────────────
@app.errorhandler(413)
def too_large(e):
    return jsonify({"status": "error", "message": "File too large. Maximum is 32 MB."}), 413


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_doc():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file in request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"status": "error", "message": "No file selected"}), 400

    filename  = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)
    logging.info("Saved: %s", file_path)

    # Create a persistent job and enqueue for sequential processing
    job_id = str(uuid.uuid4())
    _set_job(job_id, "processing", filename)
    _work_queue.put((job_id, file_path, filename))

    # Return 202 immediately — frontend will poll /status/<job_id>
    return jsonify({"status": "processing", "job_id": job_id, "file": filename}), 202


def _queue_worker():
    """Single background thread that processes files one at a time."""
    while True:
        try:
            job_id, file_path, filename = _work_queue.get()
            try:
                logging.info("[WORKER PROCESSING: %s]", filename)
                _process_file(job_id, file_path, filename)
                logging.info("[WORKER DONE: %s]", filename)
            except Exception as exc:
                logging.error("[WORKER FAILED: %s, %s]", filename, str(exc))
                logging.error("Queue worker error for %s:\n%s", filename, traceback.format_exc())
                _set_job(job_id, "error", filename, str(exc))
            finally:
                # Free memory between files
                gc.collect()
                _work_queue.task_done()
        except Exception as outer_exc:
            logging.error("Worker loop critical error:\n%s", traceback.format_exc())
            time.sleep(1)


def _process_file(job_id: str, file_path: str, filename: str):
    """Extract text → chunk → vector-index. Fast path: no graph RAG during upload."""
    try:
        start_time = time.perf_counter()

        # 1. PDF/Text Extraction
        ext_start = time.perf_counter()
        text = extract_text_from_file(file_path)
        ext_time = time.perf_counter() - ext_start

        # Delete the uploaded file after extraction to save disk
        try:
            os.remove(file_path)
        except OSError:
            pass

        if not text or not text.strip():
            _set_job(job_id, "error", filename, "No text could be extracted from this file.")
            return

        # 2. Chunking
        chunk_start = time.perf_counter()
        chunks = [text[i : i + 500] for i in range(0, len(text), 500)]
        del text  # free the full text string immediately
        chunk_time = time.perf_counter() - chunk_start

        # 3. Vector indexing (Embedding + Pinecone/Chroma Upload)
        index_start = time.perf_counter()
        vector_store.add_document(filename, chunks)
        index_time = time.perf_counter() - index_start

        total_time = time.perf_counter() - start_time
        logging.info(
            "TIMING AUDIT - File: %s\n"
            "  PDF Extraction: %.4f sec\n"
            "  Chunking: %.4f sec\n"
            "  Embedding & Vector Upload: %.4f sec\n"
            "  Total Processing Time: %.4f sec",
            filename, ext_time, chunk_time, index_time, total_time
        )

        _set_job(job_id, "done", filename, f"Indexed {len(chunks)} chunks.")
    except Exception as exc:
        logging.error("Error processing %s: %s", filename, exc, exc_info=True)
        _set_job(job_id, "error", filename, str(exc))


# Start the single sequential worker thread
_worker_thread = threading.Thread(target=_queue_worker, daemon=True)
_worker_thread.start()
logging.info("[WORKER STARTED]")

def _worker_watchdog():
    global _worker_thread
    while True:
        time.sleep(30)
        if not _worker_thread.is_alive():
            logging.error("Watchdog: Worker thread died! Respawning...")
            _worker_thread = threading.Thread(target=_queue_worker, daemon=True)
            _worker_thread.start()
            logging.info("[WORKER STARTED] (Respawned)")

_watchdog_thread = threading.Thread(target=_worker_watchdog, daemon=True)
_watchdog_thread.start()

@app.route("/health", methods=["GET"])
def health_check():
    jobs = _load_jobs()
    total = len(jobs)
    done = sum(1 for j in jobs.values() if j.get("status") == "done")
    failed = sum(1 for j in jobs.values() if j.get("status") == "error")
    processing = sum(1 for j in jobs.values() if j.get("status") == "processing")
    return jsonify({
        "status": "ok",
        "worker_alive": _worker_thread.is_alive(),
        "queue_size": _work_queue.qsize(),
        "jobs_total": total,
        "jobs_done": done,
        "jobs_failed": failed,
        "jobs_processing": processing
    })

@app.route("/status/<job_id>", methods=["GET"])
def job_status(job_id: str):
    job = _get_job(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Unknown job ID"}), 404
    return jsonify(job)


@app.route("/query", methods=["POST"])
def query_doc():
    data = request.get_json()
    if not data or not data.get("query") or not data["query"].strip():
        return jsonify({"status": "error", "message": "Missing or empty 'query' in request body"}), 400

    query = data["query"]
    try:
        results   = vector_store.query(query)
        documents = results.get("documents")
        metadatas = results.get("metadatas")

        if not documents or not documents[0]:
            return jsonify({"status": "error", "message": "No documents found. Upload documents first."}), 404

        base_chunks = documents[0][:5]
        base_metas  = metadatas[0][:5] if metadatas and metadatas[0] else []

        # ── Graph RAG: expand context via knowledge graph ──────────────────────
        augmented_chunks, augmented_metas = knowledge_graph.expand_query_context(
            query, base_chunks, base_metas
        )

        # Cap total context to avoid token overflows
        final_chunks = augmented_chunks[:8]
        final_metas  = augmented_metas[:8]

        context = "\n\n".join(final_chunks)
        graph_used = len(augmented_chunks) > len(base_chunks)
        prompt = (
            "You are a helpful assistant. Use the following document excerpts to answer the question.\n"
            + ("Note: some context was retrieved via knowledge graph traversal.\n\n" if graph_used else "\n")
            + f"Context:\n{context}\n\nQuestion: {query}\nAnswer:"
        )
        answer = groq_call_llm(prompt)
        logging.info("LLM responded successfully (graph_expanded=%s)", graph_used)

    except ValueError as e:
        logging.error("Config error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 503
    except Exception as e:
        logging.error("Query error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({
        "answer":    answer,
        "citations": final_metas,
        "graph_rag": graph_used,
        "graph_stats": knowledge_graph.stats(),
    })


@app.route("/graph/stats", methods=["GET"])
def graph_stats():
    """Return knowledge graph statistics."""
    return jsonify(knowledge_graph.stats())


# ── Blueprint ──────────────────────────────────────────────────────────────────
# Import using absolute path to avoid issues when started as a plain script
from backend.app.routes import bp as api_bp   # noqa: E402
app.register_blueprint(api_bp, url_prefix="/api")

if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)