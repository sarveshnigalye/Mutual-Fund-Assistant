"""Skip markers for tests that need resources a clean checkout (e.g. CI) does not have.

- requires_index: a built vector index under VECTORSTORE_PATH. CI gets one by extracting the
  published `data-snapshot` branch; before the first daily refresh there is none.
- requires_llm:   a GROQ_API_KEY for a live LLM answer (never set in CI).

Locally, with an index and a key in .env, these tests run as before.
"""

import os

import pytest

from app.config import settings

INDEX_FILES = ("corpus.json", "vectorizer.joblib", "tfidf_matrix.joblib", "bm25.joblib")


def index_available(path: str = None) -> bool:
    path = path or settings.vectorstore_path
    return all(os.path.exists(os.path.join(path, name)) for name in INDEX_FILES)


requires_index = pytest.mark.skipif(
    not index_available(),
    reason="No vector index (run scripts/ingest.py, or extract the data-snapshot branch into data/).",
)

requires_llm = pytest.mark.skipif(
    not (settings.groq_api_key or "").strip(),
    reason="GROQ_API_KEY not set: live LLM test.",
)
