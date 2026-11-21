"""Unit tests for the MutualFundRetriever and scheme detection."""

import pytest
from app.core.retriever import (
    MutualFundRetriever,
    detect_scheme_name,
    detect_external_amc,
)
from tests.markers import requires_index


def test_detect_scheme_name():
    assert detect_scheme_name("What is the expense ratio of HDFC Mid Cap Fund?") == "hdfc-mid-cap"
    assert detect_scheme_name("exit load for hdfc small-cap") == "hdfc-small-cap"
    assert detect_scheme_name("Tell me about HDFC Top 100 large cap") in ["hdfc-large-cap", "hdfc-large-cap"]
    assert detect_scheme_name("HDFC Silver ETF Fund of Fund details") == "hdfc-silver-etf-fof"
    assert detect_scheme_name("HDFC Multi Cap fund manager") == "hdfc-multi-cap"
    assert detect_scheme_name("What is mutual fund?") is None


def test_detect_external_amc():
    assert detect_external_amc("Tell me about SBI Blue Chip Fund") == "sbi"
    assert detect_external_amc("Axis Small Cap returns") == "axis"
    assert detect_external_amc("Nippon India Large Cap") == "nippon"
    assert detect_external_amc("What is HDFC Mid Cap expense ratio?") is None


@requires_index
def test_retriever_successful_query():
    retriever = MutualFundRetriever()
    assert retriever.load() is True

    results = retriever.retrieve("What is the expense ratio for HDFC Mid-Cap Opportunities Fund?", top_k=3)
    assert len(results) > 0

    top_chunk = results[0]
    assert "text" in top_chunk
    assert "source_url" in top_chunk
    assert "groww.in/mutual-funds/hdfc-mid-cap" in top_chunk["source_url"]
    assert top_chunk["similarity_score"] > 0.20


@requires_index
def test_retriever_external_amc_rejection():
    retriever = MutualFundRetriever()
    assert retriever.load() is True

    # Pure external query without HDFC context should yield no results
    results = retriever.retrieve("Tell me about SBI Blue Chip Fund", top_k=3)
    assert len(results) == 0


@requires_index
def test_retriever_gibberish_query():
    retriever = MutualFundRetriever()
    assert retriever.load() is True

    results = retriever.retrieve("qwerty asdfgh zxcvbn completely irrelevant", top_k=3)
    assert len(results) == 0
