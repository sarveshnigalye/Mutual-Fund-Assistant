"""ChromaDB Vector Database Store Module.

Provides embedded local vector indexing and retrieval for Phase 3.
Falls back to local hybrid store when ChromaDB is not installed or configured.
"""

import logging
from typing import Any, Dict, List, Optional

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except (ImportError, Exception):
    CHROMADB_AVAILABLE = False

from app.config import settings

logger = logging.getLogger("ingestion.chroma_store")


class ChromaVectorStore:
    """Manages local ChromaDB collection lifecycle, embeddings, and vector similarity search."""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        self.persist_directory = persist_directory or settings.chroma_db_path
        self.collection_name = collection_name or settings.vectorstore_collection
        self.client: Optional[Any] = None
        self.collection: Optional[Any] = None

        if CHROMADB_AVAILABLE:
            try:
                self.client = chromadb.PersistentClient(path=self.persist_directory)
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(f"Connected to ChromaDB collection: {self.collection_name}")
            except Exception as e:
                logger.warning(f"Could not initialize ChromaDB: {e}. Falling back to local hybrid store.")

    def is_ready(self) -> bool:
        """Returns True if ChromaDB is available and collection is initialized."""
        return self.client is not None and self.collection is not None

    def upsert_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]) -> int:
        """Upserts chunk texts, embeddings, and metadata to ChromaDB."""
        if not self.is_ready():
            logger.warning("ChromaDB is not ready. Skipping upsert.")
            return 0

        ids = [str(c["chunk_id"]) for c in chunks]
        documents = [str(c["text"]) for c in chunks]
        metadatas = [
            {
                "scheme_id": str(c.get("scheme_id", "")),
                "scheme_name": str(c.get("scheme_name", "")),
                "category": str(c.get("category", "")),
                "source_url": str(c.get("source_url", "")),
                "section_heading": str(c.get("section_heading", "")),
                "scrape_date": str(c.get("scrape_date", "2026-10-25")),
            }
            for c in chunks
        ]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(f"Successfully upserted {len(ids)} chunks to ChromaDB.")
        return len(ids)

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        scheme_filter: Optional[str] = None,
        similarity_threshold: float = 0.35,
    ) -> List[Dict[str, Any]]:
        """Searches ChromaDB collection with cosine distance and optional scheme filter."""
        if not self.is_ready():
            return []

        where_filter = None
        if scheme_filter:
            where_filter = {"scheme_id": scheme_filter}

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            formatted = []
            if results and results.get("ids"):
                ids = results["ids"][0]
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                dists = results.get("distances", [[]])[0]

                for chunk_id, doc, meta, dist in zip(ids, docs, metas, dists):
                    # Chroma returns cosine distance (1 - cosine_similarity)
                    score = 1.0 - float(dist)
                    if score < similarity_threshold:
                        continue

                    formatted.append({
                        "chunk_id": chunk_id,
                        "scheme_name": meta.get("scheme_name", ""),
                        "category": meta.get("category", ""),
                        "source_url": meta.get("source_url", ""),
                        "section_heading": meta.get("section_heading", ""),
                        "scrape_date": meta.get("scrape_date", "2026-10-25"),
                        "text": doc,
                        "similarity_score": score,
                        "cosine_score": score,
                    })
            return formatted
        except Exception as e:
            logger.error(f"ChromaDB search error: {e}")
            return []
