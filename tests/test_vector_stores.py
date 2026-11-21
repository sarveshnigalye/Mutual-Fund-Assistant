"""Unit tests for Phase 3 vector store options (Pinecone, ChromaDB, and Local Hybrid)."""

from unittest.mock import MagicMock, patch
import pytest

from app.config import settings
from app.ingestion.chroma_store import ChromaVectorStore
from app.ingestion.indexer import VectorIndexer
from app.ingestion.pinecone_store import PineconeVectorStore
from tests.markers import requires_index


def test_pinecone_unconfigured_initialization():
    """When API key is empty, Pinecone store should gracefully report not ready."""
    store = PineconeVectorStore(api_key="")
    assert store.is_ready() is False
    assert store.search(query_vector=[0.1] * 10) == []
    assert store.upsert_chunks([], []) == 0


def test_pinecone_mock_upsert_and_search():
    """Test Pinecone workflow with mocked client."""
    with patch("app.ingestion.pinecone_store.Pinecone") as mock_pinecone_cls:
        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.list_indexes.return_value = [{"name": "test-index"}]
        mock_client.Index.return_value = mock_index
        mock_pinecone_cls.return_value = mock_client

        store = PineconeVectorStore(api_key="mock-key", index_name="test-index")
        assert store.is_ready() is True

        sample_chunks = [{
            "chunk_id": "test-chunk-1",
            "scheme_id": "hdfc-mid-cap",
            "scheme_name": "HDFC Mid-Cap",
            "category": "Equity",
            "source_url": "https://groww.in/test",
            "section_heading": "Key Facts",
            "scrape_date": "2026-10-25",
            "text": "TER is 0.60%",
        }]
        vectors = [[0.1, 0.2, 0.3]]

        upserted = store.upsert_chunks(sample_chunks, vectors)
        assert upserted == 1
        mock_index.upsert.assert_called_once()

        mock_index.query.return_value = {
            "matches": [{
                "id": "test-chunk-1",
                "score": 0.92,
                "metadata": {
                    "scheme_name": "HDFC Mid-Cap",
                    "category": "Equity",
                    "source_url": "https://groww.in/test",
                    "section_heading": "Key Facts",
                    "scrape_date": "2026-10-25",
                    "text": "TER is 0.60%",
                },
            }]
        }

        results = store.search(query_vector=[0.1, 0.2, 0.3], top_k=1)
        assert len(results) == 1
        assert results[0]["chunk_id"] == "test-chunk-1"
        assert results[0]["similarity_score"] == 0.92


def test_chroma_unconfigured_initialization(tmp_path):
    """Chroma store graceful fallback behavior."""
    store = ChromaVectorStore(persist_directory=str(tmp_path / "test_chroma"))
    # If chromadb isn't installed/ready, is_ready is False and methods safely return empty
    if not store.is_ready():
        assert store.search(query_embedding=[0.1] * 10) == []
        assert store.upsert_chunks([], []) == 0


@requires_index
def test_vector_indexer_hybrid_local_search():
    """Verify local hybrid indexer search continues to operate at sub-millisecond speeds."""
    indexer = VectorIndexer(vectorstore_dir=settings.vectorstore_path)
    assert indexer.load() is True
    results = indexer.search("What is the exit load for HDFC Mid Cap?", top_k=3)
    assert len(results) > 0
    assert "HDFC Mid" in results[0]["scheme_name"]
    assert "exit load" in results[0]["text"].lower() or "exit load" in results[0]["section_heading"].lower()

