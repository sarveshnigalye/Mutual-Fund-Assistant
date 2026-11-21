"""ChromaDB Vector Database Store Module.

Provides embedded local vector indexing and retrieval for Phase 3.
Falls back to local hybrid store when ChromaDB is not installed or configured.

Phase 7: `sync_chunks` makes a re-run idempotent (upsert by deterministic ID, then delete IDs
that no longer exist), and `rename_collection` swaps a validated staging collection to live.
"""

import logging
from typing import Any, Dict, List, Optional

try:
    # Windows without the MSVC++ redistributable: chromadb's Rust bindings only find msvcp140.dll
    # after scikit-learn has loaded its bundled copy. Harmless everywhere else.
    import sklearn  # noqa: F401
except ImportError:
    pass

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except (ImportError, Exception):
    CHROMADB_AVAILABLE = False

from app.config import settings
from app.ingestion.snapshot import current_scrape_date

logger = logging.getLogger("ingestion.chroma_store")

_COLLECTION_METADATA = {"hnsw:space": "cosine"}


def clear_client_cache() -> None:
    """Forgets chromadb's per-path client cache so a replaced directory is reopened fresh."""
    if not CHROMADB_AVAILABLE:
        return
    try:
        from chromadb.api.client import SharedSystemClient

        SharedSystemClient.clear_system_cache()
    except Exception as e:  # older/newer chromadb without this API
        logger.debug(f"Could not clear chromadb client cache: {e}")


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
                    metadata=_COLLECTION_METADATA,
                )
                logger.info(f"Connected to ChromaDB collection: {self.collection_name}")
            except Exception as e:
                logger.warning(f"Could not initialize ChromaDB: {e}. Falling back to local hybrid store.")

    def is_ready(self) -> bool:
        """Returns True if ChromaDB is available and collection is initialized."""
        return self.client is not None and self.collection is not None

    def close(self) -> None:
        """Releases the client and its file handles (needed before the directory is replaced)."""
        client, self.client, self.collection = self.client, None, None
        if client is None:
            return
        try:
            close = getattr(client, "close", None)  # chromadb >= 1.x: refcounted System.stop()
            if callable(close):
                close()
            else:
                clear_client_cache()
        except Exception as e:
            logger.debug(f"Error while closing ChromaDB client: {e}")

    def count(self) -> int:
        return self.collection.count() if self.is_ready() else 0

    def _existing_dimension(self) -> Optional[int]:
        try:
            got = self.collection.get(limit=1, include=["embeddings"])
            embeddings = got.get("embeddings")
            if embeddings is not None and len(embeddings) > 0:
                return len(embeddings[0])
        except Exception:
            pass
        return None

    def reset_collection(self) -> None:
        """Drops and recreates the collection (needed when the embedding dimension changes)."""
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name, metadata=_COLLECTION_METADATA
        )

    @staticmethod
    def _metadata(c: Dict[str, Any]) -> Dict[str, str]:
        return {
            "scheme_id": str(c.get("scheme_id", "")),
            "scheme_name": str(c.get("scheme_name", "")),
            "category": str(c.get("category", "")),
            "source_url": str(c.get("source_url", "")),
            "section_heading": str(c.get("section_heading", "")),
            "scrape_date": str(c.get("scrape_date") or current_scrape_date()),
            "run_id": str(c.get("run_id", "")),
        }

    def upsert_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]) -> int:
        """Upserts chunk texts, embeddings, and metadata to ChromaDB."""
        if not self.is_ready():
            logger.warning("ChromaDB is not ready. Skipping upsert.")
            return 0
        if not chunks:
            return 0

        ids = [str(c["chunk_id"]) for c in chunks]
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=[str(c["text"]) for c in chunks],
            metadatas=[self._metadata(c) for c in chunks],
        )
        logger.info(f"Successfully upserted {len(ids)} chunks to ChromaDB.")
        return len(ids)

    def sync_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]) -> Dict[str, int]:
        """Makes the collection hold exactly `chunks`: upsert by ID, then delete stale IDs.

        TF-IDF is refit on every run, so the vector dimension follows the vocabulary. Chroma
        rejects vectors of a different dimension, so the collection is recreated when it changes.
        """
        if not self.is_ready():
            logger.warning("ChromaDB is not ready. Skipping sync.")
            return {"upserted": 0, "deleted": 0, "reset": 0}

        reset = 0
        new_dim = len(embeddings[0]) if embeddings else None
        old_dim = self._existing_dimension()
        if old_dim is not None and new_dim is not None and old_dim != new_dim:
            logger.info(f"Embedding dimension changed ({old_dim} -> {new_dim}); recreating collection.")
            self.reset_collection()
            reset = 1

        upserted = self.upsert_chunks(chunks, embeddings)

        keep = {str(c["chunk_id"]) for c in chunks}
        existing = set(self.collection.get(include=[]).get("ids", []))
        stale = sorted(existing - keep)
        if stale:
            self.collection.delete(ids=stale)
            logger.info(f"Deleted {len(stale)} stale chunks from ChromaDB.")
        return {"upserted": upserted, "deleted": len(stale), "reset": reset}

    def rename_collection(self, new_name: str) -> None:
        """Renames this collection, replacing any existing collection called `new_name`."""
        if not self.is_ready():
            raise RuntimeError("ChromaDB is not ready.")
        if new_name == self.collection_name:
            return
        try:
            self.client.delete_collection(new_name)
        except Exception:
            pass
        self.collection.modify(name=new_name)
        self.collection_name = new_name

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
                        "scrape_date": meta.get("scrape_date") or current_scrape_date(),
                        "text": doc,
                        "similarity_score": score,
                        "cosine_score": score,
                    })
            return formatted
        except Exception as e:
            logger.error(f"ChromaDB search error: {e}")
            return []
