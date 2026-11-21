"""Ingestion orchestrator: scrape → normalize → clean → chunk → embed → store.

    python scripts/ingest.py                      # rebuild the live index in place (manual run)
    python scripts/ingest.py --staging --run-id 42 --summary "$GITHUB_STEP_SUMMARY"
                                                  # daily refresh: build a staging index only

With --staging the index is written to data/vectorstore_staging/, data/chroma_staging/
(collection `mf_faq_staging`) and data/metadata_staging.json; nothing the app serves is
touched until scripts/validate_index.py passes and scripts/publish_snapshot.py promotes it.

A page that fails to scrape or is rejected by the cleaner is skipped and recorded under
`failures` in the metadata; the validation gate then blocks publishing. The script exits
non-zero only if nothing could be indexed.
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager

# Ensure project root is in sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
if __name__ == "__main__":
    os.chdir(ROOT)  # before importing app: settings read .env and data/ paths relative to the cwd

from app.config import settings
from app.ingestion import snapshot
from app.ingestion.chunker import DocumentChunker
from app.ingestion.cleaner import PageRejected, clean
from app.ingestion.indexer import VectorIndexer
from app.ingestion.normalizer import normalize
from app.ingestion.quality import extract_facts
from app.ingestion.scraper import GrowwScraper, sha256_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")


def _git_sha() -> str:
    sha = os.getenv("GITHUB_SHA")
    if sha:
        return sha
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


@contextmanager
def _stage(timings: dict, name: str):
    start = time.perf_counter()
    print(f"\n--- Stage: {name} ---")
    try:
        yield
    finally:
        timings[name] = round(time.perf_counter() - start, 3)


def run_ingestion(
    urls_path: str = "data/urls.json",
    staging: bool = False,
    run_id: str = "",
    summary_path: str = "",
    raw_dir: str = "data/raw",
    offline_html: str = "",
) -> bool:
    started = time.time()
    run_date = snapshot.ist_today()  # stamped once: every chunk of this run carries the same scrape_date
    run_id = run_id or os.getenv("GITHUB_RUN_ID") or f"local-{snapshot.ist_now().strftime('%Y%m%dT%H%M%S')}"
    if staging:
        vectorstore_dir = snapshot.STAGING_VECTORSTORE_PATH
        chroma_path = snapshot.STAGING_CHROMA_PATH
        collection = snapshot.STAGING_COLLECTION
        metadata_path = snapshot.STAGING_METADATA_PATH
        # A staging build always starts from empty, so nothing from an earlier run can leak in.
        for path in (vectorstore_dir, chroma_path):
            shutil.rmtree(path, ignore_errors=True)
        for path in (metadata_path, snapshot.VALIDATION_MARKER_PATH):
            if os.path.exists(path):
                os.remove(path)
    else:
        vectorstore_dir = settings.vectorstore_path
        chroma_path = settings.chroma_db_path
        collection = settings.vectorstore_collection
        metadata_path = settings.data_metadata_path

    print("==================================================")
    print("Mutual Fund FAQ Assistant — Ingestion Pipeline")
    print(f"Run {run_id} | {'STAGING' if staging else 'LIVE'} | provider={settings.vector_db_provider}")
    print("==================================================")

    if not os.path.exists(urls_path):
        logger.error(f"URLs file not found at: {urls_path}")
        return False
    with open(urls_path, "r", encoding="utf-8") as f:
        targets = json.load(f)
    print(f"Loaded {len(targets)} target schemes from {urls_path}")

    timings: dict = {}
    counts: dict = {}
    failures: list = []

    with _stage(timings, "scrape"):
        scraper = GrowwScraper(raw_cache_dir=raw_dir, run_date=run_date)
        if offline_html:
            logger.warning(f"OFFLINE MODE: parsing saved pages from {offline_html} (development only)")
            docs = scraper.parse_saved_pages(offline_html, urls_file=urls_path)
        else:
            docs = scraper.scrape_all(urls_file=urls_path)
        failures.extend(scraper.failures)
        counts["scrape"] = f"{len(docs)}/{len(targets)} pages"
    page_hashes = {d.scheme_id: {"page_sha256": d.page_sha256} for d in docs}

    with _stage(timings, "normalize"):
        docs = [normalize(d) for d in docs]
        counts["normalize"] = f"{len(docs)} pages"

    with _stage(timings, "clean"):
        cleaned = []
        for d in docs:
            try:
                cleaned.append(clean(d))
            except PageRejected as e:
                logger.error(f"Rejected {d.scheme_id}: {e.reason}")
                failures.append({"scheme_id": d.scheme_id, "url": d.url, "stage": "clean", "error": e.reason})
        docs = cleaned
        counts["clean"] = f"{len(docs)} pages kept"
    for d in docs:
        page_hashes[d.scheme_id]["content_sha256"] = sha256_text(d.full_text)

    if not docs:
        logger.error("No pages survived scraping and cleaning; nothing to index.")
        _write_summary(summary_path, run_id, staging, timings, counts, {}, failures, None)
        if staging:
            snapshot.write_json_atomic(metadata_path, {"run_id": run_id, "failures": failures, "total_chunks": 0})
        return False

    with _stage(timings, "chunk"):
        chunks = DocumentChunker(chunk_size=700, chunk_overlap=120, run_id=run_id).chunk_documents(docs)
        counts["chunk"] = f"{len(chunks)} chunks"

    indexer = VectorIndexer(vectorstore_dir=vectorstore_dir, chroma_path=chroma_path, chroma_collection=collection)
    extra = {
        "generated_at": snapshot.ist_now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "git_sha": _git_sha(),
        "staging": staging,
        "vector_db_provider": settings.vector_db_provider,
        "page_hashes": page_hashes,
        "failures": failures,
        "core_facts": extract_facts([c.to_dict() for c in chunks]),
    }
    catalog = indexer.index_chunks(chunks, extra_metadata=extra)
    timings["embed"] = catalog["timings"]["embed_seconds"]
    timings["store"] = catalog["timings"]["store_seconds"]
    counts["embed"] = f"vocab {catalog.get('vocab_size')}"
    chroma = catalog.get("chroma")
    counts["store"] = (
        f"{len(chunks)} chunks → vectorstore; ChromaDB `{chroma['collection']}` = {chroma['count']}"
        f" (deleted {chroma['deleted']} stale)" if chroma else f"{len(chunks)} chunks → vectorstore (ChromaDB off)"
    )
    catalog["stage_timings"] = timings
    catalog.pop("timings", None)

    # Written last: for the live index this is the signal the running backend reloads on.
    snapshot.write_json_atomic(os.path.join(vectorstore_dir, "metadata.json"), catalog)
    snapshot.write_json_atomic(metadata_path, catalog)
    print(f"✅ Wrote run metadata to {metadata_path}")

    for s_id, n in catalog["chunks_per_scheme"].items():
        print(f"   • {s_id}: {n} chunks")
    for fail in failures:
        print(f"   ❌ {fail['scheme_id']} ({fail['stage']}): {fail['error']}")

    if not staging:
        test_query = "What is the expense ratio of HDFC Mid Cap?"
        results = indexer.search(test_query, top_k=1)
        if results:
            top = results[0]
            print(f"\nVerification query '{test_query}' -> {top['scheme_name']} / {top['section_heading']} "
                  f"(score {top['similarity_score']:.3f})")
        else:
            logger.warning("Verification query returned no results!")

    _write_summary(summary_path, run_id, staging, timings, counts, catalog["chunks_per_scheme"], failures, catalog)
    print(f"\n🎉 Ingestion finished in {time.time() - started:.1f}s: {len(docs)} pages, {len(chunks)} chunks.")
    return True


def _write_summary(path, run_id, staging, timings, counts, per_scheme, failures, catalog) -> None:
    if not path:
        return
    md = [f"## 📥 Ingestion — run `{run_id}` ({'staging' if staging else 'live'})"]
    if catalog:
        md.append(f"Scrape date **{catalog.get('scrape_date')}** · generated {catalog.get('generated_at')}")
    stages = ["scrape", "normalize", "clean", "chunk", "embed", "store"]
    md.append(snapshot.md_table(
        ["Stage", "Result", "Seconds"],
        [[s, counts.get(s, "not run"), timings.get(s)] for s in stages],
    ))
    if per_scheme:
        md.append("**Chunks per scheme**\n\n" + snapshot.md_table(["Scheme", "Chunks"], list(per_scheme.items())))
    if failures:
        md.append("**Page failures**\n\n" + snapshot.md_table(
            ["Scheme", "Stage", "Error"], [[f["scheme_id"], f["stage"], f["error"]] for f in failures]
        ))
    snapshot.append_summary(path, "\n\n".join(md))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--staging", action="store_true", help="build the staging index instead of the live one")
    parser.add_argument("--run-id", default="", help="run identifier stamped on every chunk (default: $GITHUB_RUN_ID)")
    parser.add_argument("--urls", default="data/urls.json")
    parser.add_argument("--raw-dir", default="data/raw", help="where audit copies of fetched HTML are written")
    parser.add_argument("--offline-html", default="", help="DEV ONLY: parse saved <scheme_id>.html files from this "
                        "directory instead of fetching (never used by the scheduled workflow)")
    parser.add_argument("--summary", default="", help="markdown file to append a run report to")
    args = parser.parse_args(argv)
    ok = run_ingestion(args.urls, staging=args.staging, run_id=args.run_id,
                       summary_path=args.summary, raw_dir=args.raw_dir, offline_html=args.offline_html)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
