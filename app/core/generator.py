"""LLM response generator using Groq API and RAG orchestrator pipeline."""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from groq import Groq

from app.config import settings
from app.core.classifier import QueryCategory, query_classifier
from app.core.formatter import format_response
from app.core.retriever import MutualFundRetriever

logger = logging.getLogger("core.generator")

# Load prompt templates
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")
SYSTEM_PROMPT_PATH = os.path.join(PROMPT_DIR, "system_prompt.txt")

try:
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        SYSTEM_PROMPT_TEMPLATE = f.read()
except Exception as e:
    logger.warning(f"Failed to load system prompt from file: {e}")
    SYSTEM_PROMPT_TEMPLATE = (
        "You are a facts-only mutual fund FAQ assistant for HDFC Mutual Fund schemes on Groww.\n"
        "Answer ONLY factual questions based exclusively on the provided context.\n"
        "Keep your response strictly to at most 3 sentences. Do not offer investment advice."
    )


class LLMGenerator:
    """Handles LLM communication using Groq API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        self.temperature = temperature if temperature is not None else settings.llm_temperature
        self.max_tokens = max_tokens or settings.llm_max_tokens

        self.client: Optional[Groq] = None
        if self.api_key:
            self.client = Groq(api_key=self.api_key)

    def assemble_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
        """
        Assembles system instructions and user message with retrieved context.
        """
        context_blocks = []
        for i, c in enumerate(chunks, 1):
            scheme = c.get("scheme_name", "HDFC Scheme")
            section = c.get("section_heading", "Details")
            url = c.get("source_url", "")
            text = c.get("text", "")
            context_blocks.append(
                f"--- [Source {i}: {scheme} | Section: {section} | URL: {url}] ---\n{text}"
            )

        context_text = "\n\n".join(context_blocks)

        system_instruction = (
            "You are a facts-only mutual fund FAQ assistant for HDFC Mutual Fund schemes on Groww.\n"
            "STRICT RULES:\n"
            "1. Answer ONLY factual, objective questions using the provided context.\n"
            "2. Base your response EXCLUSIVELY on the verified facts in the context. Never hallucinate or speculate.\n"
            "3. State your answer clearly and concisely in at most 3 sentences.\n"
            "4. Do NOT provide investment advice, recommendations, performance predictions, or comparisons.\n"
            "5. If the context does not contain enough information to answer factually, state: "
            "'I don't have verified information on this. Please check the official HDFC AMC website: https://www.hdfcfund.com'"
        )

        user_content = (
            f"CONTEXT FROM OFFICIAL GROWW SCHEME PAGES:\n"
            f"{context_text}\n\n"
            f"USER QUERY: {query}\n\n"
            f"FACTUAL ANSWER (Max 3 sentences):"
        )

        return system_instruction, user_content

    def generate(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Calls Groq API to generate raw answer based on context chunks."""
        if not self.client:
            logger.error("Groq client not initialized (missing API key).")
            return "I don't have verified information on this. Please check the official HDFC AMC website: https://www.hdfcfund.com"

        system_prompt, user_prompt = self.assemble_prompt(query, chunks)

        try:
            chat_completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            raw_content = chat_completion.choices[0].message.content or ""
            return raw_content.strip()
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            return "I don't have verified information on this. Please check the official HDFC AMC website: https://www.hdfcfund.com"


# Re-export RAGPipeline and rag_pipeline for convenience and backwards compatibility
from app.core.rag_pipeline import RAGPipeline, rag_pipeline, rag_pipeline_instance

