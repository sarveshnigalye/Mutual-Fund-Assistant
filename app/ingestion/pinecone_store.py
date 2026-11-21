"""Pinecone Vector Database Store Module.

Provides managed cloud serverless vector indexing and retrieval for Phase 3.
Seamlessly falls back to local hybrid store when Pinecone API key is not configured.
"""

import logging
from typing import Any, Dict, List, Optional

try:
    from pinecone import Pinecone, ServerlessSpec
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False

from app.config import settings
from app.ingestion.snapshot import current_scrape_date

logger = logging.getLogger("ingestion.pinecone_store")


class PineconeVectorStore:
    """Manages Pinecone cloud index lifecycle, embedding upserts, and vector retrieval."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
        environment: Optional[str] = None,
        dimension: int = 384,
    ):
        self.api_key = api_key or settings.pinecone_api_key
        self.index_name = index_name or settings.pinecone_index_name
        self.environment = environment or settings.pinecone_environment or "us-east-1"
        self.dimension = dimension
        self.client: Optional[Any] = None
        self.index: Optional[Any] = None

        if PINECONE_AVAILABLE and self.api_key:
            try:
                self.client = Pinecone(api_key=self.api_key)
                self._connect_or_create_index()
            except Exception as e:
                logger.warning(f"Could not connect to Pinecone: {e}. Falling back to local store.")

    def is_ready(self) -> bool:
        """Returns True if Pinecone is initialized with a connected index."""
        return self.client is not None and self.index is not None

    def _connect_or_create_index(self):
        """Connects to existing Pinecone index or creates a new serverless index."""
        if not self.client:
            return

        try:
            existing_indexes = [idx["name"] for idx in self.client.list_indexes()]
            if self.index_name not in existing_indexes:
                logger.info(f"Creating Pinecone serverless index '{self.index_name}' (dim={self.dimension})...")
                self.client.create_index(
                    name=self.index_name,
                    dimension=self.dimension,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region=self.environment),
                )
            self.index = self.client.Index(self.index_name)
            logger.info(f"Connected to Pinecone index: {self.index_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone index '{self.index_name}': {e}")
            self.index = None

    def upsert_chunks(self, chunks: List[Dict[str, Any]], vectors: List[List[float]]) -> int:
        """
        Upserts chunk vectors and rich metadata to Pinecone.
        Returns the number of upserted vectors.
        """
        if not self.is_ready():
            logger.warning("Pinecone is not ready. Skipping cloud upsert.")
            return 0

        vectors_to_upsert = []
        for chunk, vec in zip(chunks, vectors):
            metadata = {
                "chunk_id": str(chunk.get("chunk_id", "")),
                "scheme_id": str(chunk.get("scheme_id", "")),
                "scheme_name": str(chunk.get("scheme_name", "")),
                "category": str(chunk.get("category", "")),
                "source_url": str(chunk.get("source_url", "")),
                "section_heading": str(chunk.get("section_heading", "")),
                "scrape_date": str(chunk.get("scrape_date") or current_scrape_date()),
                "text": str(chunk.get("text", ""))[:1000],  # Pinecone metadata size limit
            }
            vectors_to_upsert.append({
                "id": str(chunk["chunk_id"]),
                "values": [float(v) for v in vec],
                "metadata": metadata,
            })

        # Batch in sizes of 100
        batch_size = 100
        total_upserted = 0
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i : i + batch_size]
            self.index.upsert(vectors=batch)
            total_upserted += len(batch)

        logger.info(f"Successfully upserted {total_upserted} chunks into Pinecone.")
        return total_upserted

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        scheme_filter: Optional[str] = None,
        similarity_threshold: float = 0.35,
    ) -> List[Dict[str, Any]]:
        """
        Queries Pinecone index using cosine vector similarity with optional scheme metadata filtering.
        """
        if not self.is_ready():
            return []

        filter_dict = None
        if scheme_filter:
            filter_dict = {"scheme_id": {"$eq": scheme_filter}}

        try:
            res = self.index.query(
                vector=[float(v) for v in query_vector],
                top_k=top_k,
                include_metadata=True,
                filter=filter_dict,
            )

            results = []
            for match in res.get("matches", []):
                score = float(match.get("score", 0.0))
                if score < similarity_threshold:
                    continue

                meta = match.get("metadata", {})
                results.append({
                    "chunk_id": match.get("id"),
                    "scheme_name": meta.get("scheme_name", ""),
                    "category": meta.get("category", ""),
                    "source_url": meta.get("source_url", ""),
                    "section_heading": meta.get("section_heading", ""),
                    "scrape_date": meta.get("scrape_date") or current_scrape_date(),
                    "text": meta.get("text", ""),
                    "similarity_score": score,
                    "cosine_score": score,
                })
            return results
        except Exception as e:
            logger.error(f"Pinecone query error: {e}")
            return []

