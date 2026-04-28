"""
Vector storage service using ChromaDB with sentence-transformers embeddings.
Data is persisted to disk at backend/data/chroma_db/.
"""
import logging
import os
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Persist ChromaDB next to the uploaded documents
_BASE_DIR = Path(__file__).resolve().parents[3]          # SemanticSearchSystem/
_CHROMA_DIR = str(_BASE_DIR / "backend" / "data" / "chroma_db")

_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 80 MB, CPU-friendly


class VectorStore:
    """
    Persistent vector store backed by ChromaDB.
    Documents are embedded with all-MiniLM-L6-v2 and stored on disk so
    they survive server restarts.
    """

    def __init__(self, collection_name: str = "docs"):
        os.makedirs(_CHROMA_DIR, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=_CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = SentenceTransformer(_EMBED_MODEL)
        logging.info(
            "ChromaDB VectorStore ready — collection '%s', persist dir: %s",
            collection_name,
            _CHROMA_DIR,
        )

    # ------------------------------------------------------------------
    def add_document(self, doc_id: str, chunks: list[str]) -> None:
        """Embed and upsert all chunks for a document."""
        if not chunks:
            logging.warning("add_document called with empty chunk list for '%s'", doc_id)
            return

        ids = [f"{doc_id}__{i}" for i in range(len(chunks))]
        embeddings = self._embedder.encode(chunks, show_progress_bar=False).tolist()
        metadatas = [{"source": doc_id, "chunk": i} for i in range(len(chunks))]

        self._collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logging.info("Upserted %d chunks for document '%s'", len(chunks), doc_id)

    # ------------------------------------------------------------------
    def query(self, query_text: str, top_k: int = 5) -> dict:
        """
        Semantic similarity search.
        Returns a dict compatible with the original interface:
            {"documents": [[chunk, ...]], "metadatas": [[meta, ...]]}
        """
        count = self._collection.count()
        if count == 0:
            logging.warning("Vector store is empty — no documents indexed yet")
            return {"documents": [], "metadatas": []}

        query_embedding = self._embedder.encode([query_text], show_progress_bar=False).tolist()
        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=min(top_k, count),
            include=["documents", "metadatas"],
        )
        logging.info(
            "Query '%s' returned %d chunks",
            query_text,
            len(results.get("documents", [[]])[0]),
        )
        return results