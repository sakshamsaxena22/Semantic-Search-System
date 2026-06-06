# Codebase Optimization & Deployment Refactoring Summary

This document summarizes the bugs, structural changes, and optimization modifications implemented to transition the **Semantic Search System** into a clean, decoupled production state.

---

## 1. Directory & Architectural Decoupling
To enable deployment of the frontend (Vercel/GitHub Pages) separately from the backend server API (Render), the following changes were made:
* **Frontend Isolation:** Created **`frontend/index.html`** at the project root directory. The javascript code was modified with a configurable `BACKEND_URL` variable to support routing to distant Render API servers without encountering host mismatches.
* **Backend Template Route Realignment:** Updated the Flask server in **`backend/app/main.py`** to point its template folder to the root-level `frontend/` directory and render `index.html`.
* **Redundant Templates Cleaned:** Deleted the obsolete folder `backend/app/templates/` containing the duplicate `upload.html` template.

---

## 2. Dockerfile & Dependency Configuration Fixes
* **Consolidated Dependency Files:** Deleted **`requirements.prod.txt`** which was outdated, missing vital libraries (`spacy`, `networkx`), and still referencing legacy dependencies (`easyocr`).
* **Dockerfile Alignment:** Updated the root **`Dockerfile`** to copy and compile the main **`requirements.txt`** file, ensuring all Graph-RAG modules are installed during the container build.
* **Deleted Redundant Dockerfile:** Deleted **`backend/Dockerfile`** which contained incorrect command syntaxes (attempting to use `apt-get` packages inside Alpine images) and caused build path confusion on Render.
* **Whitespace Correction:** Fixed formatting spacing issues inside the primary `requirements.txt` file.

---

## 3. Resilient LLM API Client Updates
* **Query Caching:** Added a global `_llm_cache` to store LLM response outputs. Identical query prompts are resolved locally, avoiding rate limit depletion.
* **Backoff Strategy:** Enhanced the HTTP 429 response handler in **`backend/app/services/groq_client.py`** to extract and sleep the exact durations recommended by Groq headers and response message structures.
* **Retry Escalation:** Increased the API call retries from 3 to 6.

---

## 4. Documentation Additions
* Created **`docs/documentation.md`** containing the technical handover manual.
* Created **`docs/deployment_guide.md`** outlining decoupled deployment instructions for Streamlit, Vercel, Render, and Pinecone.
* Deleted duplicate root-level guide files (`documentation.md` and `deployment_guide.md`) to maintain a clean project structure.
