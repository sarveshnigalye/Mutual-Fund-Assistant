"""Retriever module for semantic vector search over mutual fund corpus."""

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings

from app.ingestion.indexer import VectorIndexer
from app.ingestion.snapshot import snapshot_version

logger = logging.getLogger("core.retriever")

# Registry of supported 5 HDFC schemes
SUPPORTED_SCHEMES = {
    "hdfc-mid-cap": {
        "canonical_name": "HDFC Mid-Cap Opportunities Fund",
        "url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        "keywords": ["mid cap", "mid-cap", "midcap", "opportunities"],
    },
    "hdfc-small-cap": {
        "canonical_name": "HDFC Small Cap Fund",
        "url": "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
        "keywords": ["small cap", "small-cap", "smallcap"],
    },
    "hdfc-large-cap": {
        "canonical_name": "HDFC Top 100 Fund",
        "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        "keywords": ["large cap", "large-cap", "largecap", "top 100", "top-100", "top100", "large and mid"],
    },
    "hdfc-silver-etf-fof": {
        "canonical_name": "HDFC Silver ETF Fund of Fund (FoF)",
        "url": "https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
        "keywords": ["silver", "silver etf", "fof", "silver fund of fund"],
    },
    "hdfc-multi-cap": {
        "canonical_name": "HDFC Multi Cap Fund",
        "url": "https://groww.in/mutual-funds/hdfc-multi-cap-fund-direct-growth",
        "keywords": ["multi cap", "multi-cap", "multicap"],
    },
}

# External AMCs to detect out-of-corpus fund queries
EXTERNAL_AMCS = [
    "sbi", "axis", "icici", "nippon", "quant", "mirae", "tata", "uti",
    "parag parikh", "ppfas", "kotak", "motilal", "dsp", "canara", "aditya birla",
    "absl", "franklin", "bandhan", "invesco", "sundaram", "edelweiss"
]


def detect_scheme_name(query: str) -> Optional[str]:
    """
    Detects which of the 5 supported HDFC schemes the user query refers to.
    Returns the scheme_id key (e.g. 'hdfc-mid-cap') or None if generic/unspecified.
    """
    query_lower = query.lower()

    # Prioritize specific multi-word / unique matches
    for scheme_id, info in SUPPORTED_SCHEMES.items():
        for kw in info["keywords"]:
            # Use word boundary where appropriate
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, query_lower):
                return scheme_id

    return None


def detect_external_amc(query: str) -> Optional[str]:
    """
    Detects whether the query references a competitor/external AMC not in our corpus.
    """
    query_lower = query.lower()
    for amc in EXTERNAL_AMCS:
        pattern = r"\b" + re.escape(amc) + r"\b"
        if re.search(pattern, query_lower):
            return amc
    return None


class MutualFundRetriever:
    """Retriever wrapping the VectorIndexer with scheme-awareness and filtering.

    Hot reload (Phase 7.9): once loaded, it checks the snapshot metadata file at most every
    `reload_check_seconds` and, when `generated_at` changes, loads the new index into a fresh
    VectorIndexer and swaps it in. If the new index cannot be loaded, the old one keeps serving.
    """

    def __init__(
        self,
        vectorstore_dir: Optional[str] = None,
        metadata_path: Optional[str] = None,
        reload_check_seconds: Optional[float] = None,
    ):
        self.vectorstore_dir = vectorstore_dir or settings.vectorstore_path
        self.metadata_path = metadata_path or settings.data_metadata_path
        self.reload_check_seconds = (
            settings.index_reload_check_seconds if reload_check_seconds is None else reload_check_seconds
        )
        self.indexer = VectorIndexer(vectorstore_dir=self.vectorstore_dir)
        self._is_loaded = False
        self._snapshot_version: Optional[str] = None
        self._last_check = 0.0
        self._lock = threading.Lock()

    @property
    def snapshot_version(self) -> Optional[str]:
        return self._snapshot_version

    def load(self) -> bool:
        """Loads vector index into memory (and picks up a newer snapshot if one was published)."""
        if not self._is_loaded:
            with self._lock:
                if not self._is_loaded:
                    version = snapshot_version(self.metadata_path)  # read before loading: never skip a newer one
                    self._is_loaded = self.indexer.load()
                    if self._is_loaded:
                        self._snapshot_version = version
                        self._last_check = time.monotonic()
            return self._is_loaded
        self._maybe_reload()
        return True

    def _maybe_reload(self) -> bool:
        now = time.monotonic()
        if now - self._last_check < self.reload_check_seconds:
            return False
        if not self._lock.acquire(blocking=False):
            return False  # another request is already checking / reloading
        try:
            self._last_check = now
            version = snapshot_version(self.metadata_path)
            if not version or version == self._snapshot_version:
                return False
            return self.reload(version)
        finally:
            self._lock.release()

    def reload(self, version: Optional[str] = None) -> bool:
        """Loads the index from disk into a fresh indexer and swaps it in on success."""
        version = version or snapshot_version(self.metadata_path)
        old = self.indexer
        if old.chroma_store is not None:
            # chromadb caches one client per path: the old one must be released (closing its file
            # handles) or the new indexer would be handed the client for the replaced directory.
            # Requests still in flight on it fall back to TF-IDF (ChromaVectorStore.search -> []).
            old.chroma_store.close()
        try:
            fresh = VectorIndexer(vectorstore_dir=self.vectorstore_dir)
            loaded = fresh.load()
        except Exception as e:  # truncated corpus.json, pickle from another scikit-learn, ...
            logger.error(f"Snapshot {version} failed to load ({type(e).__name__}: {e}).")
            loaded = False
        if not loaded:
            logger.warning(f"Snapshot {version} could not be loaded; still serving {self._snapshot_version}.")
            return False
        self.indexer = fresh
        previous, self._snapshot_version = self._snapshot_version, version
        self._is_loaded = True
        logger.info(f"Reloaded vector index: snapshot {previous} -> {version} ({len(fresh.chunks)} chunks).")
        return True

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant chunks for a user query.
        Applies scheme detection and filtering when appropriate.
        """
        if not self.load():
            logger.error("Failed to load vector index.")
            return []
        indexer = self.indexer  # one snapshot for the whole request, even if a reload swaps it

        k = top_k or settings.retrieval_top_k
        effective_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.retrieval_similarity_threshold
        )

        # Check if external AMC mentioned without any HDFC scheme
        external = detect_external_amc(query)
        detected_scheme = detect_scheme_name(query)

        if external and not detected_scheme and "hdfc" not in query.lower():
            # Query is specifically asking about a non-HDFC AMC (e.g. "SBI Blue Chip")
            logger.info(f"External AMC '{external}' detected without HDFC context.")
            return []

        # First attempt: search with scheme filter if detected
        results = []
        if detected_scheme:
            results = indexer.search(
                query=query,
                top_k=k + 3,
                scheme_filter=detected_scheme,
                similarity_threshold=effective_threshold,
            )

        # If no or too few results with filter, search globally
        if len(results) < 2:
            global_results = indexer.search(
                query=query,
                top_k=k + 3,
                scheme_filter=None,
                similarity_threshold=effective_threshold,
            )
            # Merge while avoiding duplicate chunks
            seen_ids = {r["chunk_id"] for r in results}
            for gr in global_results:
                if gr["chunk_id"] not in seen_ids:
                    results.append(gr)
                    seen_ids.add(gr["chunk_id"])

        # Filter out empty boilerplate title-only chunks (e.g. 'Details for HDFC...')
        clean_results = []
        for r in results:
            body = r["text"].split("\n", 1)[-1].strip() if "\n" in r["text"] else r["text"].strip()
            # If body is just a 1-line label like "Details for..." without any digits or data, skip
            if len(body) < 60 and not re.search(r"\d", body):
                continue
            clean_results.append(r)

        # For detected scheme, ensure its primary Key Facts chunk is included in top results
        if detected_scheme:
            key_facts_chunks = [
                c for c in indexer.chunks
                if c.get("scheme_id") == detected_scheme and "Key Facts" in c.get("section_heading", "")
            ]
            if key_facts_chunks:
                kf = key_facts_chunks[0]
                kf_id = kf["chunk_id"]
                if not any(r["chunk_id"] == kf_id for r in clean_results):
                    kf_entry = {
                        "chunk_id": kf["chunk_id"],
                        "scheme_name": kf["scheme_name"],
                        "category": kf["category"],
                        "source_url": kf["source_url"],
                        "section_heading": kf["section_heading"],
                        "scrape_date": kf["scrape_date"],
                        "text": kf["text"],
                        "similarity_score": 0.85,
                        "cosine_score": 0.85,
                    }
                    clean_results.insert(0, kf_entry)

        return clean_results[:k]
