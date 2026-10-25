"""Retriever module for semantic vector search over mutual fund corpus."""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.ingestion.indexer import VectorIndexer

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
    """Retriever wrapping the VectorIndexer with scheme-awareness and filtering."""

    def __init__(self, vectorstore_dir: Optional[str] = None):
        self.vectorstore_dir = vectorstore_dir or settings.vectorstore_path
        self.indexer = VectorIndexer(vectorstore_dir=self.vectorstore_dir)
        self._is_loaded = False

    def load(self) -> bool:
        """Loads vector index into memory."""
        if not self._is_loaded:
            self._is_loaded = self.indexer.load()
        return self._is_loaded

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
            results = self.indexer.search(
                query=query,
                top_k=k + 3,
                scheme_filter=detected_scheme,
                similarity_threshold=effective_threshold,
            )

        # If no or too few results with filter, search globally
        if len(results) < 2:
            global_results = self.indexer.search(
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
                c for c in self.indexer.chunks
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
