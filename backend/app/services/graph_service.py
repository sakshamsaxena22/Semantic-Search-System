"""
Graph RAG Service — Hybrid Entity + Relationship Extraction
============================================================

Architecture
------------
This service builds a lightweight **knowledge graph** over all ingested
document chunks and uses it to *expand* a user's query context beyond what
pure cosine similarity can find.

Pipeline
--------
1. **spaCy NER** (en_core_web_sm)
   - Runs on every chunk immediately after ingestion
   - Extracts standard entity types: PERSON, ORG, GPE, PRODUCT, EVENT, etc.
   - Free, local, fast (~80-90% coverage for general text)

2. **Groq LLM relation extraction** (selective)
   - Only triggered on "dense" chunks (>= DENSE_CHUNK_THRESHOLD chars)
   - Prompt asks for entity-relation-entity triples:
     e.g. (Python, is_used_for, data science)
   - Adds directional, typed edges to the graph (not just co-occurrence)

Graph Structure (NetworkX DiGraph)
-----------------------------------
- **Nodes**: entity strings (lowercased, stripped)
  - Attributes: entity_type (str), chunk_ids (set), sources (set)
- **Edges**: (entity_a → entity_b)
  - Attributes: relation (str), weight (int co-occurrence count)

Query Augmentation
------------------
1. Extract entities from the user query (spaCy)
2. Walk 1-hop graph neighbors of those entities
3. Collect all chunk_ids referenced by neighbor nodes
4. Return those extra chunks to enrich LLM context

Persistence
-----------
Graph is serialized to `backend/data/knowledge_graph.pkl` after every
`add_document()` call so it survives server restarts.
"""

import logging
import os
import pickle
import re
from pathlib import Path

import networkx as nx

# ── spaCy (lazy-loaded) ───────────────────────────────────────────────────────
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            logging.warning("spaCy model 'en_core_web_sm' not found. Run: python -m spacy download en_core_web_sm")
            _nlp = None
    return _nlp

# ── Config ────────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parents[3]          # SemanticSearchSystem/
_GRAPH_PATH = str(_BASE_DIR / "backend" / "data" / "knowledge_graph.pkl")

DENSE_CHUNK_THRESHOLD = 300   # chars; chunks above this get LLM relation extraction
MAX_LLM_CHUNKS_PER_DOC = 3   # limit Groq calls per document ingestion (was 10 — too slow)
GRAPH_HOP_DEPTH = 1           # how many hops to walk at query time


class KnowledgeGraph:
    """
    Persistent, hybrid-extracted knowledge graph for Graph RAG.

    Usage
    -----
    graph = KnowledgeGraph()                     # loads from disk if available
    graph.add_document("doc.pdf", chunks, groq_fn)  # ingest
    extra_chunks = graph.expand_query_context(query, base_chunk_ids, all_chunks_map)
    """

    def __init__(self):
        self._G: nx.DiGraph = nx.DiGraph()
        # chunk registry: chunk_key → chunk text
        self._chunk_registry: dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _save(self):
        try:
            with open(_GRAPH_PATH, "wb") as f:
                pickle.dump({"graph": self._G, "registry": self._chunk_registry}, f)
            logging.info("Knowledge graph saved: %d nodes, %d edges",
                         self._G.number_of_nodes(), self._G.number_of_edges())
        except Exception as e:
            logging.error("Failed to save knowledge graph: %s", e)

    def _load(self):
        if os.path.isfile(_GRAPH_PATH):
            try:
                with open(_GRAPH_PATH, "rb") as f:
                    data = pickle.load(f)
                self._G = data.get("graph", nx.DiGraph())
                self._chunk_registry = data.get("registry", {})
                logging.info("Knowledge graph loaded: %d nodes, %d edges",
                             self._G.number_of_nodes(), self._G.number_of_edges())
            except Exception as e:
                logging.warning("Could not load knowledge graph (starting fresh): %s", e)
                self._G = nx.DiGraph()
                self._chunk_registry = {}

    # ------------------------------------------------------------------
    # Entity extraction helpers
    # ------------------------------------------------------------------
    def _spacy_entities(self, text: str) -> list[tuple[str, str]]:
        """Return [(entity_text, entity_label), ...] via spaCy NER."""
        nlp = _get_nlp()
        if nlp is None:
            return []
        doc = nlp(text[:1_000_000])  # spaCy limit guard
        return [(ent.text.strip().lower(), ent.label_) for ent in doc.ents
                if len(ent.text.strip()) > 1]

    @staticmethod
    def _extract_triples_from_llm_response(text: str) -> list[tuple[str, str, str]]:
        """
        Parse LLM response for (entity, relation, entity) triples.
        Expects lines like:  (Python, is_used_for, data science)
        """
        triples = []
        for match in re.finditer(r"\(([^,]+),\s*([^,]+),\s*([^)]+)\)", text):
            a, r, b = [x.strip().lower() for x in match.groups()]
            if a and r and b and a != b:
                triples.append((a, r, b))
        return triples

    def _llm_relation_triples(self, chunk: str, groq_fn) -> list[tuple[str, str, str]]:
        """Call Groq to extract entity-relation-entity triples from a dense chunk."""
        prompt = (
            "Extract entity-relation-entity triples from the following text. "
            "Return ONLY triples in this exact format, one per line: "
            "(entity_a, relation, entity_b)\n"
            "Focus on meaningful relationships. Max 10 triples.\n\n"
            f"Text:\n{chunk[:1500]}\n\nTriples:"
        )
        try:
            response = groq_fn(prompt)
            return self._extract_triples_from_llm_response(response)
        except Exception as e:
            logging.warning("LLM relation extraction failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Graph manipulation
    # ------------------------------------------------------------------
    def _add_node(self, entity: str, etype: str, chunk_key: str, source: str):
        if not self._G.has_node(entity):
            self._G.add_node(entity, entity_type=etype, chunk_ids=set(), sources=set())
        self._G.nodes[entity]["chunk_ids"].add(chunk_key)
        self._G.nodes[entity]["sources"].add(source)

    def _add_edge(self, a: str, b: str, relation: str = "co-occurs"):
        if self._G.has_edge(a, b):
            self._G[a][b]["weight"] = self._G[a][b].get("weight", 1) + 1
        else:
            self._G.add_edge(a, b, relation=relation, weight=1)

    # ------------------------------------------------------------------
    # Public: ingestion
    # ------------------------------------------------------------------
    def add_document(self, doc_id: str, chunks: list[str], groq_fn=None) -> None:
        """
        Ingest chunks into the knowledge graph.

        Parameters
        ----------
        doc_id   : unique document identifier (e.g. filename)
        chunks   : list of text chunks
        groq_fn  : callable(prompt) -> str  — the Groq LLM function.
                   If None, LLM relation extraction is skipped.
        """
        llm_calls_made = 0

        for i, chunk in enumerate(chunks):
            chunk_key = f"{doc_id}__{i}"
            self._chunk_registry[chunk_key] = chunk

            # 1. spaCy entity extraction (always)
            entities = self._spacy_entities(chunk)
            entity_strings = []
            for ent_text, ent_label in entities:
                self._add_node(ent_text, ent_label, chunk_key, doc_id)
                entity_strings.append(ent_text)

            # Add co-occurrence edges between all entities in this chunk
            for j, ea in enumerate(entity_strings):
                for eb in entity_strings[j+1:]:
                    self._add_edge(ea, eb, "co-occurs")
                    self._add_edge(eb, ea, "co-occurs")

            # 2. LLM relation extraction (only for dense chunks, up to MAX limit)
            if (groq_fn and
                    len(chunk) >= DENSE_CHUNK_THRESHOLD and
                    llm_calls_made < MAX_LLM_CHUNKS_PER_DOC):
                triples = self._llm_relation_triples(chunk, groq_fn)
                for a, rel, b in triples:
                    # Ensure nodes exist (LLM may introduce new entities)
                    self._add_node(a, "LLM_ENTITY", chunk_key, doc_id)
                    self._add_node(b, "LLM_ENTITY", chunk_key, doc_id)
                    self._add_edge(a, b, rel)
                llm_calls_made += 1
                logging.debug("Chunk %d: LLM extracted %d relation triples", i, len(triples))

        self._save()
        # Cap registry to prevent unbounded memory growth
        if len(self._chunk_registry) > 5000:
            keys = sorted(self._chunk_registry.keys())
            for k in keys[:-5000]:
                del self._chunk_registry[k]
        logging.info(
            "Graph updated for '%s': %d nodes, %d edges",
            doc_id, self._G.number_of_nodes(), self._G.number_of_edges()
        )

    # ------------------------------------------------------------------
    # Public: query expansion
    # ------------------------------------------------------------------
    def expand_query_context(
        self,
        query: str,
        base_chunks: list[str],
        base_metadatas: list[dict],
    ) -> tuple[list[str], list[dict]]:
        """
        Augment base_chunks with graph-traversal-found related chunks.

        Parameters
        ----------
        query          : user's natural language query
        base_chunks    : chunks already retrieved by vector search
        base_metadatas : corresponding metadata dicts

        Returns
        -------
        (augmented_chunks, augmented_metadatas)
        """
        nlp = _get_nlp()
        if nlp is None or self._G.number_of_nodes() == 0:
            return base_chunks, base_metadatas

        # Extract entities from the query
        query_entities = [ent.text.strip().lower() for ent in nlp(query).ents
                          if len(ent.text.strip()) > 1]
        logging.info("Graph RAG: query entities → %s", query_entities)

        # Walk GRAPH_HOP_DEPTH hops to find related entity nodes
        related_entity_nodes: set[str] = set()
        for qe in query_entities:
            if self._G.has_node(qe):
                # BFS up to GRAPH_HOP_DEPTH hops
                visited = {qe}
                frontier = {qe}
                for _ in range(GRAPH_HOP_DEPTH):
                    next_frontier = set()
                    for node in frontier:
                        neighbors = set(self._G.successors(node)) | set(self._G.predecessors(node))
                        next_frontier |= neighbors - visited
                    visited |= next_frontier
                    frontier = next_frontier
                related_entity_nodes |= visited - {qe}

        # Collect chunk keys from those nodes
        graph_chunk_keys: set[str] = set()
        for node in related_entity_nodes:
            graph_chunk_keys |= self._G.nodes[node].get("chunk_ids", set())

        # Retrieve chunk texts for found keys, deduplicated against base_chunks
        extra_chunks: list[str] = []
        extra_metas: list[dict] = []
        for key in sorted(graph_chunk_keys)[:10]:   # cap at 10 extra chunks
            text = self._chunk_registry.get(key, "")
            if text and text not in base_chunks:
                parts = key.split("__")
                source = parts[0] if parts else key
                chunk_idx = int(parts[1]) if len(parts) > 1 else 0
                extra_chunks.append(text)
                extra_metas.append({"source": source, "chunk": chunk_idx, "via": "graph"})

        logging.info(
            "Graph RAG: %d base chunks + %d graph-expanded chunks (from %d related entities)",
            len(base_chunks), len(extra_chunks), len(related_entity_nodes)
        )

        return base_chunks + extra_chunks, base_metadatas + extra_metas

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def stats(self) -> dict:
        """Return graph statistics dict."""
        return {
            "nodes": self._G.number_of_nodes(),
            "edges": self._G.number_of_edges(),
            "chunks_indexed": len(self._chunk_registry),
        }
