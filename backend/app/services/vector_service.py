"""
Vector storage service using ChromaDB with sentence-transformers embeddings.
Data is persisted to disk at backend/data/chroma_db/.
"""
import logging
import os
from pathlib import Path

# Persist ChromaDB next to the uploaded documents
_BASE_DIR = Path(__file__).resolve().parents[3]          # SemanticSearchSystem/
_CHROMA_DIR = str(_BASE_DIR / "backend" / "data" / "chroma_db")

_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 80 MB, CPU-friendly

# ── Lazy-loaded embedder (avoid loading 400 MB of PyTorch at import time) ─────
_embedder = None

def _get_embedder():
    """Return the SentenceTransformer model, loading it on first use."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        logging.info("Loading SentenceTransformer model '%s'...", _EMBED_MODEL)
        _embedder = SentenceTransformer(_EMBED_MODEL)
        logging.info("SentenceTransformer model loaded.")
    return _embedder


class VectorStore:
    """
    Vector store backing. Supports production Pinecone DB if PINECONE_API_KEY
    is configured, otherwise falls back to local persistent ChromaDB.
    """

    def __init__(self, collection_name: str = "docs"):
        
        self.pinecone_api_key = os.environ.get("PINECONE_API_KEY", "")
        self.pinecone_index_name = os.environ.get("PINECONE_INDEX_NAME", "")

        if self.pinecone_api_key and self.pinecone_index_name:
            self._use_pinecone = True
            self._pinecone_initialized = False
            logging.info(
                "Pinecone VectorStore ready — Index: %s",
                self.pinecone_index_name
            )
        else:
            self._use_pinecone = False
            self._collection_name = collection_name
            self._chroma_initialized = False
            logging.info(
                "VectorStore configured for ChromaDB — collection '%s' (lazy init)",
                collection_name,
            )

    def _ensure_pinecone(self):
        """Lazy-initialize the Pinecone client on first actual use."""
        if not self._pinecone_initialized:
            from pinecone import Pinecone
            self._pc = Pinecone(api_key=self.pinecone_api_key)
            self._index = self._pc.Index(self.pinecone_index_name)
            self._pinecone_initialized = True
            logging.info(
                "Pinecone VectorStore ready — Index: %s",
                self.pinecone_index_name
            )

    def _ensure_chroma(self):
        """Lazy-initialize the ChromaDB client on first actual use."""
        if not self._chroma_initialized:
            import chromadb
            from chromadb.config import Settings
            os.makedirs(_CHROMA_DIR, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=_CHROMA_DIR,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma_initialized = True
            logging.info(
                "ChromaDB VectorStore ready — collection '%s', persist dir: %s",
                self._collection_name,
                _CHROMA_DIR,
            )

    # ------------------------------------------------------------------
    def add_document(self, doc_id: str, chunks: list[str]) -> None:
        """Embed and upsert all chunks for a document."""
        if not chunks:
            logging.warning("add_document called with empty chunk list for '%s'", doc_id)
            return

        embeddings = _get_embedder().encode(chunks, show_progress_bar=False).tolist()

        if self._use_pinecone:
            self._ensure_pinecone()
            vectors = []
            for i, chunk in enumerate(chunks):
                vectors.append((
                    f"{doc_id}__{i}",
                    embeddings[i],
                    {
                        "source": doc_id,
                        "chunk": i,
                        "text": chunk
                    }
                ))
            # Upsert vectors to Pinecone
            self._index.upsert(vectors=vectors)
            logging.info("Upserted %d chunks to Pinecone for document '%s'", len(chunks), doc_id)
        else:
            self._ensure_chroma()
            ids = [f"{doc_id}__{i}" for i in range(len(chunks))]
            metadatas = [{"source": doc_id, "chunk": i} for i in range(len(chunks))]
            self._collection.upsert(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            logging.info("Upserted %d chunks to ChromaDB for document '%s'", len(chunks), doc_id)

    # ------------------------------------------------------------------
    def query(self, query_text: str, top_k: int = 5) -> dict:
        """
        Semantic similarity search.
        Returns a dict compatible with the original interface:
            {"documents": [[chunk, ...]], "metadatas": [[meta, ...]]}
        """
        query_embedding = _get_embedder().encode([query_text], show_progress_bar=False).tolist()

        if self._use_pinecone:
            self._ensure_pinecone()
            results = self._index.query(
                vector=query_embedding[0],
                top_k=top_k,
                include_metadata=True
            )
            
            documents = []
            metadatas = []
            for match in results.get("matches", []):
                meta = match.get("metadata", {})
                documents.append(meta.get("text", ""))
                metadatas.append({
                    "source": meta.get("source", ""),
                    "chunk": int(meta.get("chunk", 0))
                })
            
            logging.info(
                "Pinecone query '%s' returned %d chunks",
                query_text,
                len(documents),
            )
            return {"documents": [documents], "metadatas": [metadatas]}
        else:
            self._ensure_chroma()
            count = self._collection.count()
            if count == 0:
                logging.warning("Vector store is empty — no documents indexed yet")
                return {"documents": [], "metadatas": []}

            results = self._collection.query(
                query_embeddings=query_embedding,
                n_results=min(top_k, count),
                include=["documents", "metadatas"],
            )
            logging.info(
                "ChromaDB query '%s' returned %d chunks",
                query_text,
                len(results.get("documents", [[]])[0]),
            )
            return results