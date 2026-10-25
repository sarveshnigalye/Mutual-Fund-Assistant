"""Unit tests for the LLM Generator and RAG Pipeline with mocked Groq API."""

from unittest.mock import MagicMock, patch
import pytest

from app.core.generator import LLMGenerator
from app.core.rag_pipeline import RAGPipeline


def test_assemble_prompt_structure():
    generator = LLMGenerator()
    chunks = [
        {
            "scheme_name": "HDFC Mid-Cap Opportunities Fund",
            "section_heading": "Expense Ratio",
            "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
            "text": "The expense ratio is 0.60%.",
        }
    ]
    system_prompt, user_prompt = generator.assemble_prompt(
        query="What is the expense ratio?",
        chunks=chunks,
    )

    assert "STRICT RULES" in system_prompt
    assert "facts-only" in system_prompt.lower()
    assert "HDFC Mid-Cap Opportunities Fund" in user_prompt
    assert "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth" in user_prompt
    assert "What is the expense ratio?" in user_prompt


def test_generator_with_mocked_llm_success():
    generator = LLMGenerator(api_key="mock_key", model="mock-model")

    mock_choice = MagicMock()
    mock_choice.message.content = "The expense ratio of HDFC Mid-Cap Fund is 0.60%."
    mock_response = MagicMock(choices=[mock_choice])

    with patch.object(generator.client.chat.completions, "create", return_value=mock_response) as mock_create:
        chunks = [{"scheme_name": "HDFC Mid Cap", "text": "Expense ratio: 0.60%", "source_url": "https://groww.in/url"}]
        result = generator.generate("What is the expense ratio?", chunks)

        assert result == "The expense ratio of HDFC Mid-Cap Fund is 0.60%."
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["max_tokens"] == 300


def test_generator_api_error_fallback():
    generator = LLMGenerator(api_key="mock_key")

    with patch.object(generator.client.chat.completions, "create", side_effect=Exception("API connection timeout")):
        result = generator.generate("What is the expense ratio?", [])
        assert "I don't have verified information on this" in result
        assert "https://www.hdfcfund.com" in result


def test_rag_pipeline_fallback_on_unindexed_scheme():
    pipeline = RAGPipeline()
    # Query with non-indexed competitor scheme
    res = pipeline.run("What is the expense ratio of SBI Blue Chip Fund?")
    assert "I don't have verified information on this" in res.response
    assert "https://www.hdfcfund.com" in res.response
    assert res.source_url == "https://www.hdfcfund.com"
