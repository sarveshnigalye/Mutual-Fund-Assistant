"""Script to test chunk retrieval for the user's specific questions."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.retriever import MutualFundRetriever
from app.core.rag_pipeline import rag_pipeline

def test_queries():
    retriever = MutualFundRetriever()
    retriever.load()

    queries = [
        "What's the expense ratio of HDFC large cap mutual fund?",
        "What's the NAV of HDFC large cap mutual fund?"
    ]

    for i, q in enumerate(queries, 1):
        print("=" * 80)
        print(f"QUERY {i}: \"{q}\"")
        print("=" * 80)

        # 1. Test Retriever
        chunks = retriever.retrieve(q, top_k=3)
        print(f"Total retrieved chunks: {len(chunks)}")
        for rank, c in enumerate(chunks, 1):
            print(f"\n[Rank #{rank}] Chunk ID: {c['chunk_id']}")
            print(f"  • Scheme:  {c['scheme_name']}")
            print(f"  • Section: {c['section_heading']}")
            print(f"  • Score:   {c['similarity_score']:.4f}")
            print(f"  • Source:  {c['source_url']}")
            print(f"  • Text Snippet:\n    {c['text'][:250]}...")

        # 2. Test End-to-End RAG Pipeline Response
        print("\n--- End-to-End RAG Pipeline Response ---")
        rag_res = rag_pipeline(q)
        print(rag_res.response)
        print("\n")

if __name__ == "__main__":
    test_queries()

