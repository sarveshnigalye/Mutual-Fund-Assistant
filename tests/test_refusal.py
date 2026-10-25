"""Unit tests for refusal templates and safety pipeline behavior."""

import pytest
from app.core.classifier import QueryCategory, query_classifier
from app.core.generator import rag_pipeline


def test_refusal_advisory():
    refusal = query_classifier.get_refusal(QueryCategory.ADVISORY, "Should I invest?")
    assert "SEBI-registered" in refusal
    assert "https://investor.sebi.gov.in" in refusal


def test_refusal_comparative():
    refusal = query_classifier.get_refusal(QueryCategory.COMPARATIVE, "Which is better?")
    assert "cannot compare funds" in refusal
    assert "https://www.hdfcfund.com" in refusal


def test_refusal_pii():
    refusal = query_classifier.get_refusal(QueryCategory.PII_DETECTED, "My PAN is ABCDE1234F")
    assert "⚠️ Please do not share personal information" in refusal


def test_refusal_performance_dynamic_url():
    refusal_mid = query_classifier.get_refusal(QueryCategory.PERFORMANCE, "returns of HDFC Mid Cap")
    assert "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth" in refusal_mid

    refusal_generic = query_classifier.get_refusal(QueryCategory.PERFORMANCE, "What are the returns?")
    assert "https://www.hdfcfund.com" in refusal_generic


def test_refusal_out_of_scope():
    refusal = query_classifier.get_refusal(QueryCategory.OUT_OF_SCOPE, "weather today")
    assert "outside my scope" in refusal
    assert "amfiindia.com" in refusal


def test_pipeline_refuses_advisory_query():
    res = rag_pipeline.run("Should I invest in HDFC Mid Cap Fund?")
    assert res["is_refusal"] is True
    assert res["category"] == "ADVISORY"
    assert "SEBI-registered" in res["response"]
    assert len(res["retrieved_chunks"]) == 0


def test_pipeline_refuses_pii_query():
    res = rag_pipeline.run("My Aadhaar is 2345 6789 0123, what is my folio?")
    assert res["is_refusal"] is True
    assert res["category"] == "PII_DETECTED"
    assert "⚠️ Please do not share personal information" in res["response"]
