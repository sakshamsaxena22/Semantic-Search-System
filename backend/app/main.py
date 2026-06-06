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

# ── App setup ──────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=os.path.join(APP_DIR, "templates"))
app.config["UPLOAD_FOLDER"]      = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024   # 32 MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ── Shared state ───────────────────────────────────────────────────────────────
vector_store   = VectorStore()
knowledge_graph = KnowledgeGraph()

# job_id → {"status": "processing"|"done"|"error", "file": str, "message": str}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ── Error handlers ─────────────────────────────────────────────────────────────
@app.errorhandler(413)
def too_large(e):
    return jsonify({"status": "error", "message": "File too large. Maximum is 32 MB."}), 413


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("upload.html")


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

    # Create a job and process in the background so the browser never times out
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "processing", "file": filename, "message": ""}

    threading.Thread(
        target=_process_file,
        args=(job_id, file_path, filename),
        daemon=True,
    ).start()

    # Return 202 immediately — frontend will poll /status/<job_id>
    return jsonify({"status": "processing", "job_id": job_id, "file": filename}), 202


def _process_file(job_id: str, file_path: str, filename: str):
    """Background worker: extract text → chunk → vector-index → graph-index."""
    try:
        text = extract_text_from_file(file_path)
        if not text or not text.strip():
            with _jobs_lock:
                _jobs[job_id] = {
                    "status": "error",
                    "file": filename,
                    "message": "No text could be extracted from this file.",
                }
            return

        chunks = [text[i : i + 500] for i in range(0, len(text), 500)]

        # Step 1: index into ChromaDB vector store
        vector_store.add_document(filename, chunks)
        logging.info("Vector-indexed '%s' — %d chunks", filename, len(chunks))

        # Step 2: index into knowledge graph (hybrid spaCy + selective Groq)
        try:
            knowledge_graph.add_document(filename, chunks, groq_fn=groq_call_llm)
        except Exception as graph_exc:
            # Graph indexing failure is non-fatal — vector search still works
            logging.warning("Graph indexing failed for '%s': %s", filename, graph_exc)

        with _jobs_lock:
            _jobs[job_id] = {
                "status": "done",
                "file": filename,
                "message": f"Indexed {len(chunks)} chunks.",
            }
    except Exception as exc:
        logging.error("Error processing %s: %s", filename, exc, exc_info=True)
        with _jobs_lock:
            _jobs[job_id] = {
                "status": "error",
                "file": filename,
                "message": str(exc),
            }


@app.route("/status/<job_id>", methods=["GET"])
def job_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
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