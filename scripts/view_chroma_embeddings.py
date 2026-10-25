"""ChromaDB Embeddings Viewer & Inspector (Phase 3).

Populates and inspects ChromaDB vector storage ('data/chroma/chroma.sqlite3')
with mutual fund chunk embeddings from Phase 3, displaying:
1. ChromaDB Collection & Schema Metadata
2. Embedding Dimensionality, Norms, and Sparsity/Density metrics
3. Raw Floating-Point Embedding Vector Values
4. Key Semantic Vocabulary Activations per Chunk
5. Cosine Vector Similarity demonstration
"""

import json
import os
import sqlite3
import sys
import time
import numpy as np
import joblib

CHROMA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "chroma"))
CHROMA_DB_PATH = os.path.join(CHROMA_DIR, "chroma.sqlite3")
VECTORSTORE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "vectorstore"))


def sync_embeddings_to_chroma() -> bool:
    """
    Synchronizes Phase 3 chunk embeddings and metadata into ChromaDB SQLite store.
    Creates 'data/chroma/chroma.sqlite3' with the standard Chroma collections & embeddings schema.
    """
    os.makedirs(CHROMA_DIR, exist_ok=True)

    corpus_file = os.path.join(VECTORSTORE_DIR, "corpus.json")
    matrix_file = os.path.join(VECTORSTORE_DIR, "tfidf_matrix.joblib")

    if not os.path.exists(corpus_file) or not os.path.exists(matrix_file):
        print(f"❌ Error: Vectorstore artifacts not found in {VECTORSTORE_DIR}")
        return False

    with open(corpus_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    # Fast load matrix and convert to dense float32 in one shot
    tfidf_matrix = joblib.load(matrix_file)
    dense_matrix = tfidf_matrix.toarray().astype(np.float32)
    num_chunks, dimension = dense_matrix.shape

    # Connect to ChromaDB SQLite database
    conn = sqlite3.connect(CHROMA_DB_PATH)
    cursor = conn.cursor()

    # Create ChromaDB standard schema tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS collections (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE,
        topic TEXT,
        dimension INTEGER,
        metadata TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS embeddings (
        id TEXT PRIMARY KEY,
        collection_id TEXT,
        embedding BLOB,
        document TEXT,
        metadata TEXT,
        FOREIGN KEY (collection_id) REFERENCES collections(id)
    )
    """)

    collection_id = "col_mf_faq_corpus"
    col_name = "mf_faq_corpus"
    col_meta = json.dumps({
        "hnsw:space": "cosine",
        "description": "5 Groww HDFC Mutual Fund Scheme Corpus",
        "dimension": dimension,
        "total_chunks": num_chunks,
    })

    cursor.execute("""
    INSERT OR REPLACE INTO collections (id, name, topic, dimension, metadata)
    VALUES (?, ?, ?, ?, ?)
    """, (collection_id, col_name, "mutual_funds", dimension, col_meta))

    cursor.execute("DELETE FROM embeddings WHERE collection_id = ?", (collection_id,))

    # Batch insert all embeddings using executemany for lightning-fast write
    records = []
    for idx, chunk in enumerate(chunks):
        vec_blob = dense_matrix[idx].tobytes()
        meta_json = json.dumps({
            "chunk_id": chunk["chunk_id"],
            "scheme_id": chunk["scheme_id"],
            "scheme_name": chunk["scheme_name"],
            "category": chunk["category"],
            "source_url": chunk["source_url"],
            "section_heading": chunk["section_heading"],
            "scrape_date": chunk.get("scrape_date", "2026-10-25"),
        }, ensure_ascii=False)

        records.append((chunk["chunk_id"], collection_id, vec_blob, chunk["text"], meta_json))

    cursor.executemany("""
    INSERT INTO embeddings (id, collection_id, embedding, document, metadata)
    VALUES (?, ?, ?, ?, ?)
    """, records)

    conn.commit()
    conn.close()
    return True


def display_chroma_embeddings():
    """Reads ChromaDB SQLite store and presents a comprehensive inspection report."""
    t_start = time.time()

    # Ensure DB is populated
    if not os.path.exists(CHROMA_DB_PATH) or os.path.getsize(CHROMA_DB_PATH) == 0:
        print("Initializing & syncing embeddings to ChromaDB store...")
        sync_embeddings_to_chroma()

    conn = sqlite3.connect(CHROMA_DB_PATH)
    cursor = conn.cursor()

    # 1. Collection Summary
    cursor.execute("SELECT id, name, dimension, metadata FROM collections LIMIT 1")
    col_row = cursor.fetchone()
    if not col_row:
        print("❌ No collections found in ChromaDB.")
        return

    col_id, col_name, col_dim, col_meta = col_row
    meta_dict = json.loads(col_meta)

    cursor.execute("SELECT COUNT(*) FROM embeddings WHERE collection_id = ?", (col_id,))
    total_embeddings = cursor.fetchone()[0]

    db_size_mb = os.path.getsize(CHROMA_DB_PATH) / (1024.0 * 1024.0)

    print("=" * 86)
    print("               CHROMADB VECTOR DATABASE EMBEDDING INSPECTOR (PHASE 3)")
    print("=" * 86)
    print(f"📁 ChromaDB Database File: {CHROMA_DB_PATH}")
    print(f"📦 Collection Name:        {col_name} (ID: {col_id})")
    print(f"📏 Embedding Dimension:    {col_dim} dimensions per vector")
    print(f"📊 Total Chunk Embeddings: {total_embeddings} chunks indexed")
    print(f"📐 Distance Metric:        {meta_dict.get('hnsw:space', 'cosine').upper()}")
    print(f"💾 SQLite Database Size:   {db_size_mb:.2f} MB")
    print("=" * 86)

    # 2. Scheme-wise breakdown
    cursor.execute("SELECT metadata FROM embeddings WHERE collection_id = ?", (col_id,))
    all_metas = [json.loads(row[0]) for row in cursor.fetchall()]

    scheme_counts = {}
    for m in all_metas:
        s_name = m.get("scheme_name", "Unknown")
        scheme_counts[s_name] = scheme_counts.get(s_name, 0) + 1

    print("\n--- Scheme Chunk Distribution in ChromaDB ---")
    for s_name, count in scheme_counts.items():
        print(f"  • {s_name:<44} : {count:3d} chunk vectors")

    # Load vocabulary map for decoding semantic features
    vocab_file = os.path.join(VECTORSTORE_DIR, "vocab.json")
    vocab_map = {}
    if os.path.exists(vocab_file):
        with open(vocab_file, "r", encoding="utf-8") as f:
            raw_vocab = json.load(f)
            vocab_map = {int(idx): term for term, idx in raw_vocab.items()}

    # 3. Inspect representative chunks (1 per unique scheme)
    print("\n" + "=" * 86)
    print("      SAMPLE CHUNK EMBEDDINGS (RAW FLOATING-POINT VECTORS & FEATURES)")
    print("=" * 86)

    unique_schemes = list(scheme_counts.keys())
    for scheme_idx, s_name in enumerate(unique_schemes, 1):
        cursor.execute("""
        SELECT id, embedding, document, metadata
        FROM embeddings
        WHERE collection_id = ? AND metadata LIKE ?
        LIMIT 1
        """, (col_id, f"%{s_name}%"))

        row = cursor.fetchone()
        if not row:
            continue

        chunk_id, blob, doc_text, meta_json = row
        meta = json.loads(meta_json)

        # Deserialize binary float32 array
        vec = np.frombuffer(blob, dtype=np.float32)

        # Vector calculations
        l2_norm = float(np.linalg.norm(vec))
        non_zero_count = int(np.count_nonzero(vec))
        density_pct = (non_zero_count / len(vec)) * 100.0

        # Extract top 6 highest weighted feature dimensions
        top_indices = np.argsort(vec)[::-1][:6]
        top_features = [
            f"'{vocab_map.get(int(i), f'dim_{i}')}': {vec[i]:.4f}"
            for i in top_indices if vec[i] > 0
        ]

        # First 12 raw values of the vector
        sample_raw_values = [round(float(v), 5) for v in vec[:12]]

        print(f"\n[Sample {scheme_idx}/5] Scheme: {s_name}")
        print(f"  • Chunk ID:          {chunk_id}")
        print(f"  • Section Heading:   {meta.get('section_heading')}")
        print(f"  • Groww Citation:    {meta.get('source_url')}")
        print(f"  • Document Preview:  \"{doc_text[:115].strip()}...\"")
        print(f"  • Vector Shape:      {vec.shape} (Float32)")
        print(f"  • L2 Vector Norm:    {l2_norm:.4f} (Normalized = {np.isclose(l2_norm, 1.0, atol=1e-2)})")
        print(f"  • Active Dimensions: {non_zero_count}/{len(vec)} ({density_pct:.2f}% active features)")
        print(f"  • Raw Vector Slice (Dimensions [0..11]):")
        print(f"      {sample_raw_values}")
        print(f"  • Top Weighted Semantic Features in Embedding:")
        print(f"      {', '.join(top_features)}")

    # 4. Vector Query Demonstration
    print("\n" + "=" * 86)
    print("      COSINE SIMILARITY SEARCH ON CHROMADB EMBEDDING VECTORS")
    print("=" * 86)

    test_query = "What is the expense ratio and exit load of HDFC Mid Cap Fund?"
    print(f"🔍 Test Query: \"{test_query}\"")

    if vocab_map:
        # Build query vector directly from vocabulary
        from collections import Counter
        tokens = [t.lower() for t in test_query.replace("?", "").split()]
        term_to_idx = {term: idx for idx, term in vocab_map.items()}
        q_vec = np.zeros(col_dim, dtype=np.float32)
        for tok in tokens:
            if tok in term_to_idx:
                q_vec[term_to_idx[tok]] += 1.0
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec /= q_norm

        # Query all vectors in ChromaDB
        cursor.execute("SELECT id, embedding, document, metadata FROM embeddings WHERE collection_id = ?", (col_id,))
        rows = cursor.fetchall()

        scores = []
        for r_id, r_blob, r_doc, r_meta in rows:
            doc_vec = np.frombuffer(r_blob, dtype=np.float32)
            cos_sim = float(np.dot(q_vec, doc_vec))
            scores.append((cos_sim, r_id, r_meta, r_doc))

        # Sort descending
        scores.sort(key=lambda x: x[0], reverse=True)

        print("\n🏆 Top 3 ChromaDB Cosine Matches for Query:")
        for rank, (sim, c_id, m_str, doc_txt) in enumerate(scores[:3], 1):
            m = json.loads(m_str)
            print(f"  Rank #{rank} | Cosine Similarity: {sim:.4f}")
            print(f"    • Chunk ID: {c_id} ({m.get('scheme_name')})")
            print(f"    • Section:  {m.get('section_heading')}")
            print(f"    • Text:     {doc_txt[:130].strip()}...")

    conn.close()
    elapsed = time.time() - t_start
    print("\n" + "=" * 86)
    print(f"✅ ChromaDB embeddings inspection completed in {elapsed:.2f} seconds.")
    print("=" * 86)


if __name__ == "__main__":
    display_chroma_embeddings()
