"""Unit tests for Phase 1 Data Ingestion Pipeline."""

import json
import os
import pytest

from app.ingestion.chunker import DocumentChunk, DocumentChunker
from app.ingestion.indexer import VectorIndexer
from app.ingestion.scraper import ScrapedDocument


def test_urls_json_contents():
    """Verify data/urls.json has exactly 5 Groww HDFC URLs with required fields."""
    urls_path = "data/urls.json"
    assert os.path.exists(urls_path), f"{urls_path} does not exist"

    with open(urls_path, "r", encoding="utf-8") as f:
        urls = json.load(f)

    assert len(urls) == 5, f"Expected exactly 5 URLs, found {len(urls)}"

    expected_ids = {
        "hdfc-mid-cap",
        "hdfc-small-cap",
        "hdfc-large-cap",
        "hdfc-silver-etf-fof",
        "hdfc-multi-cap",
    }
    found_ids = {u["id"] for u in urls}
    assert found_ids == expected_ids

    for u in urls:
        assert "groww.in/mutual-funds/hdfc" in u["url"]
        assert u["type"] == "groww"
        assert "HDFC" in u["scheme_name"]


def test_document_chunker_basic():
    """Test chunking logic and metadata propagation."""
    doc = ScrapedDocument(
        scheme_id="test-fund",
        scheme_name="HDFC Test Fund",
        category="Test Category",
        url="https://groww.in/mutual-funds/test-fund",
        amc="HDFC Mutual Fund",
        scrape_date="2026-10-25",
        full_text="Some full text here.",
        sections=[
            {
                "section": "Expense Ratio & Exit Load",
                "text": "The expense ratio of HDFC Test Fund is 0.75%. The exit load is 1% if redeemed within 1 year.",
            },
            {
                "section": "SIP & Minimums",
                "text": "The minimum SIP amount is 500 rupees. Minimum lumpsum investment is 1000 rupees.",
            },
        ],
    )

    chunker = DocumentChunker(chunk_size=500, chunk_overlap=100)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) >= 2
    for c in chunks:
        assert c.scheme_id == "test-fund"
        assert c.source_url == "https://groww.in/mutual-funds/test-fund"
        assert c.document_type == "groww"
        assert c.scrape_date == "2026-10-25"
        assert len(c.text) > 20


def test_vector_indexer_search(tmp_path):
    """Test indexing and retrieval using VectorIndexer."""
    indexer = VectorIndexer(vectorstore_dir=str(tmp_path))

    chunks = [
        DocumentChunk(
            chunk_id="chunk-001",
            scheme_id="hdfc-mid-cap",
            scheme_name="HDFC Mid-Cap Opportunities Fund",
            category="Mid Cap",
            source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
            document_type="groww",
            section_heading="Expense Ratio",
            scrape_date="2026-10-25",
            text="[HDFC Mid-Cap Opportunities Fund - Expense Ratio]\nExpense ratio is 0.74%. Total TER includes management fee.",
        ),
        DocumentChunk(
            chunk_id="chunk-002",
            scheme_id="hdfc-small-cap",
            scheme_name="HDFC Small Cap Fund",
            category="Small Cap",
            source_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
            document_type="groww",
            section_heading="Exit Load",
            scrape_date="2026-10-25",
            text="[HDFC Small Cap Fund - Exit Load]\nExit load of 1% is charged if units are redeemed within 1 year from allotment.",
        ),
    ]

    catalog = indexer.index_chunks(chunks)
    assert catalog["total_chunks"] == 2

    # Query for expense ratio
    results = indexer.search("What is the expense ratio of HDFC Mid Cap?", top_k=1)
    assert len(results) == 1
    assert results[0]["chunk_id"] == "chunk-001"
    assert results[0]["source_url"] == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
    assert results[0]["similarity_score"] > 0.2
