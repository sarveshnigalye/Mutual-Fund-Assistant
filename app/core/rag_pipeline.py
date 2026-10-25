"""RAG Orchestrator Pipeline coordinating Retriever, Generator, and Formatter."""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.classifier import QueryCategory, query_classifier
from app.core.formatter import format_response
from app.core.generator import LLMGenerator
from app.core.retriever import MutualFundRetriever

logger = logging.getLogger("core.rag_pipeline")


class FormattedResponse(BaseModel):
    """Structured response model returned by the RAG orchestrator pipeline."""
    query: str = Field(..., description="Original user query")
    response: str = Field(..., description="Formatted final response")
    raw_response: str = Field(..., description="Raw generation from LLM or refusal text")
    source_url: Optional[str] = Field(default=None, description="Cited Groww source URL")
    scrape_date: Optional[str] = Field(default=None, description="Data currency date")
    category: str = Field(default="FACTUAL", description="Query safety classification category")
    is_refusal: bool = Field(default=False, description="Whether query was refused on safety/scope grounds")
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

    def run(self, query: str, top_k: int = 5) -> FormattedResponse:
        """
        Executes complete RAG pipeline:
        query -> safety classification -> (refusal OR retrieval -> generation -> formatting)
        """
        # 1. Safety classification
        category = self.classifier.classify(query)

        if category != QueryCategory.FACTUAL:
            refusal_text = self.classifier.get_refusal(category, query)
            return FormattedResponse(
                query=query,
                response=refusal_text,
                raw_response=refusal_text,
                source_url=None,
                scrape_date=None,
                category=category.value,
                is_refusal=True,
                retrieved_chunks=[],
            )

        # 2. Retrieve chunks
        chunks = self.retriever.retrieve(query=query, top_k=top_k)

        # 3. Check if relevant context was found
        if not chunks:
            fallback_text = (
                "I don't have verified information on this. "
                "Please check the official HDFC AMC website: https://www.hdfcfund.com"
            )
            formatted_fallback = format_response(fallback_text, source_url="", scrape_date="2026-10-25")
            return FormattedResponse(
                query=query,
                response=formatted_fallback,
                raw_response=fallback_text,
                source_url="https://www.hdfcfund.com",
                scrape_date="2026-10-25",
                category=QueryCategory.FACTUAL.value,
                is_refusal=False,
                retrieved_chunks=[],
            )

        # 4. Determine top source url and scrape date
        top_chunk = chunks[0]
        source_url = top_chunk.get("source_url", "")
        scrape_date = top_chunk.get("scrape_date", "2026-10-25")

        # 5. Generate raw response via LLM
        raw_response = self.generator.generate(query=query, chunks=chunks)

        # 6. Format and enforce constraints (<=3 sentences, citation link, footer)
        formatted = format_response(
            raw_response=raw_response,
            source_url=source_url,
            scrape_date=scrape_date,
        )

        return FormattedResponse(
            query=query,
            response=formatted,
            raw_response=raw_response,
            source_url=source_url,
            scrape_date=scrape_date,
            category=QueryCategory.FACTUAL.value,
            is_refusal=False,
            retrieved_chunks=chunks,
        )

    def __call__(self, query: str, top_k: int = 5) -> FormattedResponse:
        """Allows calling rag_pipeline(query) directly as a callable."""
        return self.run(query=query, top_k=top_k)


# Global orchestrator pipeline instance
rag_pipeline = RAGPipeline()
rag_pipeline_instance = rag_pipeline

