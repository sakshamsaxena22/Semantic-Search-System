"""
Main application file for the chatbot service.
Run this from the project root directory (chatbot_theme_identifier).
"""
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import logging

# Import local modules using relative imports
from backend.app.services.ocr_service import extract_text_from_file
from backend.app.services.vector_service import VectorStore
from backend.app.services.groq_client import groq_call_llm

# Base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Create Flask app with correct template path
app = Flask(__name__, template_folder=os.path.join(APP_DIR, "templates"))

# Setup upload folder
UPLOAD_FOLDER = os.path.join(BASE_DIR, "backend", "data")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB per file

# Create upload folder if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Enable CORS
CORS(app)  # Consider restricting origins for production

# Setup logging
logging.basicConfig(level=logging.INFO)

# Initialize vector store
vector_store = VectorStore()


@app.errorhandler(413)
def too_large(e):
    return jsonify({"status": "error", "message": "File too large. Maximum upload size is 32 MB."}), 413

@app.route("/")
def home():
    return render_template("upload.html")  # Make sure upload.html is in app/templates/

@app.route("/upload", methods=["POST"])
def upload_doc():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part in the request"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "No file selected"}), 400
        
    filename = secure_filename(file.filename or "")
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    
    try:
        file.save(file_path)
        logging.info(f"Saved file to {file_path}")
        
        # Extract text
        text = extract_text_from_file(file_path)
        if not text:
            return jsonify({"status": "error", "message": "No text extracted from file"}), 400
            
        # Split into chunks
        chunks = [text[i:i+500] for i in range(0, len(text), 500)]
        
        # Add to vector store
        vector_store.add_document(filename, chunks)
        logging.info(f"Added document '{filename}' to vector store")
    except Exception as e:
        logging.error(f"Error processing file {filename}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
        
    return jsonify({"status": "success", "file": filename})

@app.route("/query", methods=["POST"])
def query_doc():
    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"status": "error", "message": "Missing 'query' in request body"}), 400

    query = data["query"]

    try:
        # Query vector store
        results = vector_store.query(query)
        documents = results.get("documents")
        metadatas = results.get("metadatas")

        if not documents or not documents[0]:
            return jsonify({"status": "error", "message": "No documents found. Please upload documents first."}), 404

        # Limit to top 5 chunks to keep prompt within model context
        top_chunks = documents[0][:5]
        top_meta   = metadatas[0][:5] if metadatas and metadatas[0] else []

        context = "\n\n".join(top_chunks)
        prompt = (
            f"You are a helpful assistant. Use the following document excerpts to answer the question.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {query}\nAnswer:"
        )

        answer = groq_call_llm(prompt)
        logging.info("LLM responded successfully")
    except ValueError as e:
        # Missing / invalid API key
        logging.error(f"Configuration error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 503
    except Exception as e:
        logging.error(f"Error during query processing: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"answer": answer, "citations": top_meta})

# Register blueprints
from backend.app.routes import bp as api_bp
app.register_blueprint(api_bp, url_prefix='/api')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)