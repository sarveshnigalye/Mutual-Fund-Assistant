"""Ingestion orchestrator script.
Scrapes the 5 Groww HDFC mutual fund scheme pages, chunks the content,
generates embeddings, and indexes everything into persistent storage.
"""

import json
import logging
import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ingestion.chunker import DocumentChunker
from app.ingestion.indexer import VectorIndexer
from app.ingestion.scraper import GrowwScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")


def run_ingestion(urls_path: str = "data/urls.json") -> bool:
    start_time = time.time()
    print("==================================================")
    print("Mutual Fund FAQ Assistant — Ingestion Pipeline")
    print("==================================================")

    if not os.path.exists(urls_path):
        logger.error(f"URLs file not found at: {urls_path}")
        return False

    with open(urls_path, "r", encoding="utf-8") as f:
        urls_data = json.load(f)

    print(f"Loaded {len(urls_data)} target schemes from {urls_path}:")
    for i, item in enumerate(urls_data, 1):
        print(f" {i}. {item['scheme_name']} ({item['category']}) -> {item['url']}")

    # 1. Scrape all 5 Groww Scheme pages
    print("\n--- Step 1: Scraping Scheme Pages ---")
    scraper = GrowwScraper(raw_cache_dir="data/raw")
    scraped_docs = scraper.scrape_all(urls_file=urls_path)

    if not scraped_docs:
        logger.error("Scraping failed: No documents returned.")
        return False

    print(f"✅ Successfully scraped {len(scraped_docs)} documents.")

    # 2. Chunk documents
    print("\n--- Step 2: Chunking Extracted Content ---")
    chunker = DocumentChunker(chunk_size=700, chunk_overlap=120)
    all_chunks = chunker.chunk_documents(scraped_docs)
    print(f"✅ Generated {len(all_chunks)} chunks across {len(scraped_docs)} schemes.")

    # Print breakdown per scheme
    scheme_chunk_counts = {}
    for c in all_chunks:
        scheme_chunk_counts[c.scheme_name] = scheme_chunk_counts.get(c.scheme_name, 0) + 1

    for s_name, count in scheme_chunk_counts.items():
        print(f"   • {s_name}: {count} chunks")

    # 3. Embed and Index chunks
    print("\n--- Step 3: Vector Indexing & Embedding ---")
    indexer = VectorIndexer(vectorstore_dir="data/vectorstore")
    catalog = indexer.index_chunks(all_chunks)

    # 4. Copy summary metadata to data/metadata.json for root accessibility
    with open("data/metadata.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print("✅ Exported catalog metadata to data/metadata.json")

    # 5. Run Verification Query
    print("\n--- Step 4: Verification Similarity Query ---")
    test_query = "What is the expense ratio of HDFC Mid Cap?"
    print(f"Running test query: '{test_query}'")
    results = indexer.search(test_query, top_k=2)

    if results:
        top_match = results[0]
        print(f"✅ Top Match Chunk ID: {top_match['chunk_id']}")
        print(f"✅ Scheme: {top_match['scheme_name']}")
        print(f"✅ Section: {top_match['section_heading']}")
        print(f"✅ Score: {top_match['similarity_score']:.4f}")
        print(f"✅ Citation URL: {top_match['source_url']}")
        print(f"✅ Date Stamp: {top_match['scrape_date']}")
        print(f"✅ Sample Text snippet:\n   {top_match['text'][:200]}...")
    else:
        logger.warning("Verification query returned no results!")

    elapsed = time.time() - start_time
    print("\n==================================================")
    print(f"🎉 INGESTION COMPLETE in {elapsed:.2f} seconds!")
    print(f"   Total Schemes: {len(scraped_docs)}")
    print(f"   Total Chunks:  {len(all_chunks)}")
    print(f"   Storage:       data/vectorstore/")
    print("==================================================")
    return True


if __name__ == "__main__":
    success = run_ingestion()
    sys.exit(0 if success else 1)
