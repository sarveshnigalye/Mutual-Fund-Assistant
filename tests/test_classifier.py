"""Unit tests for the query classifier and safety guardrails."""

import pytest
from app.core.classifier import QueryCategory, query_classifier


def test_factual_classification():
    factual_queries = [
        "What is the expense ratio of HDFC Mid Cap?",
        "What is the exit load for HDFC Small Cap Fund?",
        "What is the minimum SIP amount for HDFC Top 100?",
        "Who is the fund manager of HDFC Multi Cap Fund?",
        "What is the benchmark index of HDFC Silver ETF FoF?",
    ]
    for q in factual_queries:
        cat = query_classifier.classify(q)
        assert cat == QueryCategory.FACTUAL, f"Expected FACTUAL for query: {q}, got {cat}"


def test_advisory_classification():
    advisory_queries = [
        "Should I invest in HDFC Mid Cap Fund?",
        "Which fund do you recommend for long term growth?",
        "Is HDFC Small Cap a good fund to buy?",
        "Will HDFC Multi Cap fund outperform the market?",
        "Suggest the best fund to invest 10000 rupees",
    ]
    for q in advisory_queries:
        cat = query_classifier.classify(q)
        assert cat == QueryCategory.ADVISORY, f"Expected ADVISORY for query: {q}, got {cat}"


def test_comparative_classification():
    comparative_queries = [
        "Which is better — HDFC Mid Cap or HDFC Small Cap?",
        "Compare HDFC Large Cap vs HDFC Multi Cap",
        "What is the difference between Mid Cap and Large Cap?",
    ]
    for q in comparative_queries:
        cat = query_classifier.classify(q)
        assert cat == QueryCategory.COMPARATIVE, f"Expected COMPARATIVE for query: {q}, got {cat}"


def test_pii_classification():
    pii_queries = [
        "My PAN is ABCDE1234F, check my balance",
        "Call me on +91 9876543210 regarding my fund",
        "My email address is investor@example.com",
        "My bank account number is 123456789012",
    ]
    for q in pii_queries:
        cat = query_classifier.classify(q)
        assert cat == QueryCategory.PII_DETECTED, f"Expected PII_DETECTED for query: {q}, got {cat}"


def test_performance_classification():
    performance_queries = [
        "What are the 5-year returns of HDFC Mid Cap?",
        "What is the CAGR of HDFC Small Cap?",
        "How much profit or return did HDFC Multi Cap give?",
    ]
    for q in performance_queries:
        cat = query_classifier.classify(q)
        assert cat == QueryCategory.PERFORMANCE, f"Expected PERFORMANCE for query: {q}, got {cat}"


def test_out_of_scope_classification():
    oos_queries = [
        "What is the weather today?",
        "Who is the Prime Minister of India?",
        "Write a poem about mutual funds",
    ]
    for q in oos_queries:
        cat = query_classifier.classify(q)
        assert cat == QueryCategory.OUT_OF_SCOPE, f"Expected OUT_OF_SCOPE for query: {q}, got {cat}"
