"""Unit tests for the response formatter covering all edge cases."""

import pytest
from app.core.formatter import clean_llm_output, format_response, split_sentences


def test_clean_llm_output():
    raw = "<think>The user is asking about expense ratio.</think>The expense ratio is 0.60%."
    cleaned = clean_llm_output(raw)
    assert cleaned == "The expense ratio is 0.60%."
    assert "<think>" not in cleaned


def test_split_sentences_with_decimals_and_abbr():
    text = "HDFC Asset Management Co. Ltd. manages the fund. The expense ratio is 0.60%. The minimum SIP is ₹100. It is rated 4 stars."
    sentences = split_sentences(text)
    assert len(sentences) == 4
    assert sentences[0] == "HDFC Asset Management Co. Ltd. manages the fund."
    assert "0.60%" in sentences[1]


def test_formatter_edge_case_zero_sentences():
    # 0 sentences / empty string
    formatted = format_response(
        raw_response="   \n\t  ",
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        scrape_date="2026-10-25",
    )
    assert "I don't have verified information on this" in formatted
    assert "https://www.hdfcfund.com" in formatted
    assert "_Last updated from sources: 2026-10-25_" in formatted


def test_formatter_edge_case_many_sentences_capped_at_three():
    # 7 sentences should be capped strictly at 3
    raw = (
        "First sentence states the expense ratio. Second sentence explains exit load. "
        "Third sentence details the benchmark. Fourth sentence should be dropped. "
        "Fifth sentence dropped. Sixth sentence dropped. Seventh sentence dropped."
    )
    formatted = format_response(
        raw_response=raw,
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        scrape_date="2026-10-25",
    )
    assert "First sentence states the expense ratio." in formatted
    assert "Second sentence explains exit load." in formatted
    assert "Third sentence details the benchmark." in formatted
    assert "Fourth sentence" not in formatted
    assert "Fifth sentence" not in formatted
    assert "📎 Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth" in formatted
    assert "_Last updated from sources: 2026-10-25_" in formatted


def test_formatter_edge_case_missing_url():
    # When source_url is empty, no "📎 Source:" line should be added
    raw = "The minimum SIP amount for HDFC Top 100 Fund is ₹100."
    formatted = format_response(
        raw_response=raw,
        source_url="",
        scrape_date="2026-10-25",
    )
    assert "The minimum SIP amount for HDFC Top 100 Fund is ₹100." in formatted
    assert "📎 Source:" not in formatted
    assert "_Last updated from sources: 2026-10-25_" in formatted


def test_format_response_pii_safety_net():
    raw_with_pii = "Your account number is 123456789012. The expense ratio is 0.60%."
    formatted = format_response(
        raw_response=raw_with_pii,
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    )
    assert "⚠️ Please do not share personal information" in formatted
    assert "123456789012" not in formatted
