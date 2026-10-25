"""Vector store indexer module for storing and querying mutual fund corpus."""

import json
import logging
import os
from typing import Any, Dict, List, Optional
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.config import settings
from app.ingestion.chunker import DocumentChunk
from app.ingestion.embedder import CorpusEmbedder, tokenize_text
from app.ingestion.pinecone_store import PineconeVectorStore
from app.ingestion.chroma_store import ChromaVectorStore

logger = logging.getLogger("ingestion.indexer")


class VectorIndexer:
    """Manages persistent indexing, metadata persistence, and similarity search.

    Supports Pinecone (cloud), ChromaDB (embedded), and local serialized hybrid store.
    """

    def __init__(self, vectorstore_dir: str = "data/vectorstore"):
        self.vectorstore_dir = vectorstore_dir
        os.makedirs(self.vectorstore_dir, exist_ok=True)

        self.corpus_path = os.path.join(self.vectorstore_dir, "corpus.json")
        self.metadata_path = os.path.join(self.vectorstore_dir, "metadata.json")

        self.embedder = CorpusEmbedder(vectorstore_dir=self.vectorstore_dir)
        self.chunks: List[Dict[str, Any]] = []

        # Cloud and embedded provider integrations (Phase 3 §3.4)
        self.provider = settings.vector_db_provider
        self.pinecone_store = (
            PineconeVectorStore() if self.provider == "pinecone" else None
        )
        self.chroma_store = (
            ChromaVectorStore() if self.provider == "chromadb" else None
        )

    def index_chunks(self, chunk_objects: List[DocumentChunk]) -> Dict[str, Any]:
        """
        Indexes chunks into persistent storage and builds vector representations.
        """
        logger.info(f"Indexing {len(chunk_objects)} chunks...")

        # 1. Save corpus chunks to JSON
        self.chunks = [c.to_dict() for c in chunk_objects]
        with open(self.corpus_path, "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, indent=2, ensure_ascii=False)

        # 2. Fit TF-IDF & BM25 models
        fit_results = self.embedder.fit_and_encode(chunk_objects)

        # 3. Create metadata catalog
        schemes = list({c.scheme_name for c in chunk_objects})
        urls = list({c.source_url for c in chunk_objects})
        scrape_date = chunk_objects[0].scrape_date if chunk_objects else ""

        catalog = {
            "total_chunks": len(chunk_objects),
            "total_schemes": len(schemes),
            "schemes": schemes,
            "source_urls": urls,
            "scrape_date": scrape_date,
            "embedding_type": "tfidf_bm25_hybrid",
            "corpus_path": self.corpus_path,
        }

        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)

        # 4. Optional cloud / embedded database sync (Pinecone / ChromaDB)
        if self.pinecone_store and self.pinecone_store.is_ready():
            dense_vectors = self.embedder.tfidf_matrix.toarray().tolist()
            self.pinecone_store.upsert_chunks(self.chunks, dense_vectors)

        if self.chroma_store and self.chroma_store.is_ready():
            dense_vectors = self.embedder.tfidf_matrix.toarray().tolist()
            self.chroma_store.upsert_chunks(self.chunks, dense_vectors)

        logger.info(f"Indexing complete. {len(chunk_objects)} chunks indexed across {len(schemes)} schemes.")
        return catalog

    def load(self) -> bool:
        """Loads indexed corpus and vectors into memory."""
        if not os.path.exists(self.corpus_path):
            return False

        with open(self.corpus_path, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)

        return self.embedder.load()

    def search(
        self,
        query: str,
        top_k: int = 5,
        scheme_filter: Optional[str] = None,
        similarity_threshold: float = 0.15,
    ) -> List[Dict[str, Any]]:
        """
        Performs hybrid similarity search (TF-IDF Cosine Similarity + BM25) over the corpus.
        Optionally filters by scheme name.
        """
        if not self.chunks or self.embedder.vectorizer is None:
            if not self.load():
                logger.error("No indexed corpus found to query.")
                return []

        # Check if Pinecone cloud provider is active (Phase 3 §3.4)
        if self.pinecone_store and self.pinecone_store.is_ready():
            q_dense = self.embedder.transform_query(query).toarray()[0].tolist()
            pinecone_results = self.pinecone_store.search(
                query_vector=q_dense,
                top_k=top_k,
                scheme_filter=scheme_filter,
                similarity_threshold=similarity_threshold,
            )
            if pinecone_results:
                return pinecone_results

        # Check if ChromaDB local provider is active (Phase 3 §3.4)
        if self.chroma_store and self.chroma_store.is_ready():
            q_dense = self.embedder.transform_query(query).toarray()[0].tolist()
            chroma_results = self.chroma_store.search(
                query_embedding=q_dense,
                top_k=top_k,
                scheme_filter=scheme_filter,
                similarity_threshold=similarity_threshold,
            )
            if chroma_results:
                return chroma_results

        # 1. Cosine similarity via TF-IDF
        q_vec = self.embedder.transform_query(query)
        cos_sims = cosine_similarity(q_vec, self.embedder.tfidf_matrix)[0]

        # 2. BM25 scores
        q_tokens = tokenize_text(query)
        bm25_scores = np.array(self.embedder.bm25.get_scores(q_tokens)) if self.embedder.bm25 else np.zeros(len(self.chunks))

        # Normalize BM25 scores using expected reference scale (min denominator 10.0)
        bm25_max = np.max(bm25_scores) if len(bm25_scores) > 0 and np.max(bm25_scores) > 0 else 1.0
        norm_scale = max(bm25_max, 10.0)
        norm_bm25 = np.where(cos_sims > 0, bm25_scores / norm_scale, 0.0)

        # 3. Hybrid scoring (70% vector cosine similarity + 30% BM25 lexical match)
        hybrid_scores = 0.7 * cos_sims + 0.3 * norm_bm25

        # 4. Rank candidates
        ranked_indices = np.argsort(hybrid_scores)[::-1]

        results = []
        for idx in ranked_indices:
            score = float(hybrid_scores[idx])
            cos_score = float(cos_sims[idx])

            # Filter candidates that don't meet threshold
            if score < similarity_threshold or cos_score < 0.10:
                continue

            chunk = self.chunks[idx]

            # Apply scheme filter if specified
            if scheme_filter:
                filter_lower = scheme_filter.lower()
                chunk_scheme = chunk["scheme_name"].lower()
                chunk_id = chunk["scheme_id"].lower()
                if filter_lower not in chunk_scheme and filter_lower not in chunk_id:
                    continue

            result_entry = {
                "chunk_id": chunk["chunk_id"],
                "scheme_name": chunk["scheme_name"],
                "category": chunk["category"],
                "source_url": chunk["source_url"],
                "section_heading": chunk["section_heading"],
                "scrape_date": chunk["scrape_date"],
                "text": chunk["text"],
                "similarity_score": score,
                "cosine_score": cos_score,
            }
            results.append(result_entry)

            if len(results) >= top_k:
                break

        return results
