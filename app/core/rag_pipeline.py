"""RAG Orchestrator Pipeline coordinating Preprocessing, Classifier, Retriever, Generator and Formatter."""

import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.classifier import REFUSAL_TEMPLATES, QueryCategory, query_classifier
from app.core.formatter import (
    FALLBACK_SOURCE_URL,
    FALLBACK_TEXT,
    default_scrape_date,
    format_response,
)
from app.core.generator import LLMGenerator
from app.core.preprocess import preprocess_query
from app.core.retriever import MutualFundRetriever, detect_external_amc, detect_scheme_name
from app.core.safety import scan_pii

logger = logging.getLogger("core.rag_pipeline")

NON_ENGLISH_TEXT = REFUSAL_TEMPLATES.get(
    "NON_ENGLISH", "I currently support English queries only. Please rephrase your question in English."
)
INVALID_INPUT_TEXT = REFUSAL_TEMPLATES.get(
    "INVALID_INPUT", "Please enter a question about HDFC Mutual Fund schemes."
)
NON_INDEXED_TEXT = REFUSAL_TEMPLATES.get(
    "NON_INDEXED",
    "I don't have verified information on this. I only cover five HDFC Mutual Fund schemes, "
    "so please check the official website of the relevant fund house.",
)

# Phrases in the LLM's own output that mean "no answer in context"
_NO_INFO_RE = re.compile(
    r"(?i)\b(?:i\s+don'?t\s+have\s+verified\s+information|"
    r"(?:the\s+)?(?:provided\s+)?context\s+does\s+not\s+(?:contain|include|mention)|"
    r"not\s+(?:available|mentioned)\s+in\s+the\s+(?:provided\s+)?context)\b"
)
# Advisory language that must never leak into a factual answer (edge-cases.md §5.6)
_ADVISORY_OUTPUT_RE = re.compile(
    r"(?i)\b(?:you\s+should\s+(?:invest|buy|sell|consider)|i\s+(?:would\s+)?recommend|"
    r"(?:is|a)\s+(?:a\s+)?(?:good|great|excellent|bad|poor)\s+(?:fund|investment|choice|option)|"
    r"worth\s+investing|ideal\s+for\s+(?:long[\s-]term|investors)|suitable\s+for\s+you)\b"
)


class FormattedResponse(BaseModel):
    """Structured response model returned by the RAG orchestrator pipeline."""
    query: str = Field(..., description="Original user query")
    response: str = Field(..., description="Formatted final response")
    raw_response: str = Field(..., description="Raw generation from LLM or refusal text")
    source_url: Optional[str] = Field(default=None, description="Cited Groww source URL")
    scrape_date: Optional[str] = Field(default=None, description="Data currency date")
    category: str = Field(default="FACTUAL", description="Query safety classification category")
    is_refusal: bool = Field(default=False, description="Whether query was refused on safety/scope grounds")
    truncated: bool = Field(default=False, description="Whether the query was trimmed to 500 chars")
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list, description="Retrieved context chunks")

    def get(self, key: str, default: Any = None) -> Any:
        """Supports dict-like .get() access for backwards compatibility."""
        return getattr(self, key, default)

    def __getitem__(self, item: str) -> Any:
        """Supports dict subscript access."""
        return getattr(self, item)


class RAGPipeline:
    """End-to-end RAG orchestrator coordinating classification, retrieval, generation, and formatting."""

    def __init__(
        self,
        retriever: Optional[MutualFundRetriever] = None,
        generator: Optional[LLMGenerator] = None,
        classifier=None,
    ):
        self.retriever = retriever or MutualFundRetriever()
        self.generator = generator or LLMGenerator()
        self.classifier = classifier or query_classifier

    @staticmethod
    def _refusal(query: str, text: str, category: str, truncated: bool = False) -> FormattedResponse:
        return FormattedResponse(
            query=query,
            response=text,
            raw_response=text,
            source_url=None,
            scrape_date=None,
            category=category,
            is_refusal=True,
            truncated=truncated,
            retrieved_chunks=[],
        )

    @staticmethod
    def _fallback(query: str, text: str, raw: str, chunks=None, truncated: bool = False) -> FormattedResponse:
        scrape_date = default_scrape_date()
        return FormattedResponse(
            query=query,
            response=format_response(text, source_url=FALLBACK_SOURCE_URL, scrape_date=scrape_date),
            raw_response=raw,
            source_url=FALLBACK_SOURCE_URL,
            scrape_date=scrape_date,
            category=QueryCategory.FACTUAL.value,
            is_refusal=False,
            truncated=truncated,
            retrieved_chunks=chunks or [],
        )

    def run(self, query: str, top_k: int = 5) -> FormattedResponse:
        """
        query -> preprocess -> safety classification
              -> (refusal | retrieval -> generation -> output guard -> formatting)
        """
        original_query = query or ""

        # 0. PII scan on the ORIGINAL text — sanitising strips '@' etc. and could hide an email
        has_pii, _ = scan_pii(original_query)
        if has_pii:
            return self._refusal(
                original_query,
                self.classifier.get_refusal(QueryCategory.PII_DETECTED),
                QueryCategory.PII_DETECTED.value,
            )

        # 1. Pre-processing (edge-cases.md §1): empty/short, HTML/special chars, language, length
        pre = preprocess_query(original_query)
        if pre.status == "INVALID":
            return self._refusal(original_query, INVALID_INPUT_TEXT, "INVALID_INPUT")
        if pre.status == "NON_ENGLISH":
            return self._refusal(original_query, NON_ENGLISH_TEXT, QueryCategory.OUT_OF_SCOPE.value)
        clean_query = pre.clean

        # 2. Safety classification (Layer 1 heuristics, Layer 2 LLM only if inconclusive)
        category = self.classifier.classify(clean_query)

        if category != QueryCategory.FACTUAL:
            if category == QueryCategory.INCONCLUSIVE:
                category = QueryCategory.OUT_OF_SCOPE
            refusal_text = self.classifier.get_refusal(category, clean_query)
            return self._refusal(original_query, refusal_text, category.value, pre.truncated)

        # 2. Non-indexed AMC (edge-cases.md §2.12)
        if detect_external_amc(clean_query) and not detect_scheme_name(clean_query) and "hdfc" not in clean_query.lower():
            return self._fallback(original_query, NON_INDEXED_TEXT, NON_INDEXED_TEXT, truncated=pre.truncated)

        # 3. Retrieve chunks
        chunks = self.retriever.retrieve(query=clean_query, top_k=top_k)
        if not chunks:
            return self._fallback(original_query, FALLBACK_TEXT, FALLBACK_TEXT, truncated=pre.truncated)

        top_chunk = chunks[0]
        source_url = top_chunk.get("source_url") or FALLBACK_SOURCE_URL
        scrape_date = top_chunk.get("scrape_date") or default_scrape_date()

        # 4. Generate raw response via LLM
        raw_response = self.generator.generate(query=clean_query, chunks=chunks)

        # 5. Output guards
        if not raw_response.strip() or _NO_INFO_RE.search(raw_response):
            # The model found nothing usable: don't cite an unrelated scheme page
            return self._fallback(original_query, FALLBACK_TEXT, raw_response, chunks, pre.truncated)
        if _ADVISORY_OUTPUT_RE.search(raw_response):
            logger.warning("Advisory language detected in LLM output; replacing with refusal.")
            return self._refusal(
                original_query,
                self.classifier.get_refusal(QueryCategory.ADVISORY, clean_query),
                QueryCategory.ADVISORY.value,
                pre.truncated,
            )

        # 6. Format and enforce constraints (<=3 sentences, one citation, footer)
        formatted = format_response(raw_response=raw_response, source_url=source_url, scrape_date=scrape_date)

        return FormattedResponse(
            query=original_query,
            response=formatted,
            raw_response=raw_response,
            source_url=source_url,
            scrape_date=scrape_date,
            category=QueryCategory.FACTUAL.value,
            is_refusal=False,
            truncated=pre.truncated,
            retrieved_chunks=chunks,
        )

    def __call__(self, query: str, top_k: int = 5) -> FormattedResponse:
        """Allows calling rag_pipeline(query) directly as a callable."""
        return self.run(query=query, top_k=top_k)


# Global orchestrator pipeline instance
rag_pipeline = RAGPipeline()
rag_pipeline_instance = rag_pipeline
