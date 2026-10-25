"""Embedding and Vector representation generator."""

import os
import re
from typing import Any, Dict, List, Tuple
import joblib
import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.ingestion.chunker import DocumentChunk


def tokenize_text(text: str) -> List[str]:
    """Tokenizes text for BM25 indexing."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return [w for w in cleaned.split() if len(w) > 1]


class CorpusEmbedder:
    """Manages TF-IDF vectorization and BM25 token modeling for the mutual fund corpus."""

    def __init__(self, vectorstore_dir: str = "data/vectorstore"):
        self.vectorstore_dir = vectorstore_dir
        os.makedirs(self.vectorstore_dir, exist_ok=True)

        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self.bm25: Optional[BM25Okapi] = None
        self.chunks: List[DocumentChunk] = []

    def fit_and_encode(self, chunks: List[DocumentChunk]) -> Dict[str, Any]:
        """
        Fits TF-IDF and BM25 models over all chunk texts.
        Generates and saves the vector matrices.
        """
        self.chunks = chunks
        corpus_texts = [c.text for c in chunks]

        # 1. Fit TF-IDF Vectorizer (unigrams + bigrams, sublinear tf)
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            norm="l2",
            stop_words="english",
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus_texts)

        # 2. Fit BM25 Okapi
        tokenized_corpus = [tokenize_text(t) for t in corpus_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)

        # 3. Save serialized artifacts
        vectorizer_path = os.path.join(self.vectorstore_dir, "vectorizer.joblib")
        matrix_path = os.path.join(self.vectorstore_dir, "tfidf_matrix.joblib")
        bm25_path = os.path.join(self.vectorstore_dir, "bm25.joblib")

        joblib.dump(self.vectorizer, vectorizer_path)
        joblib.dump(self.tfidf_matrix, matrix_path)
        joblib.dump(self.bm25, bm25_path)

        return {
            "total_chunks": len(chunks),
            "vocab_size": len(self.vectorizer.vocabulary_),
            "vectorizer_path": vectorizer_path,
            "matrix_path": matrix_path,
            "bm25_path": bm25_path,
        }

    def load(self) -> bool:
        """Loads trained vectorizer, matrix, and BM25 from disk if present."""
        vectorizer_path = os.path.join(self.vectorstore_dir, "vectorizer.joblib")
        matrix_path = os.path.join(self.vectorstore_dir, "tfidf_matrix.joblib")
        bm25_path = os.path.join(self.vectorstore_dir, "bm25.joblib")

        if (
            os.path.exists(vectorizer_path)
            and os.path.exists(matrix_path)
            and os.path.exists(bm25_path)
        ):
            self.vectorizer = joblib.load(vectorizer_path)
            self.tfidf_matrix = joblib.load(matrix_path)
            self.bm25 = joblib.load(bm25_path)
            return True
        return False

    def transform_query(self, query: str):
        """Converts user query into a vector in the corpus TF-IDF space."""
        if not self.vectorizer:
            raise RuntimeError("Embedder not fitted or loaded yet.")
        return self.vectorizer.transform([query])
