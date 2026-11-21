"""Validation gate for a freshly built index (Phase 7.7).

    python scripts/validate_index.py --staging --previous origin/data-snapshot \
        --require-today --require-chroma --summary "$GITHUB_STEP_SUMMARY"

FAILS (exit 1, blocks publishing) on: a page failure recorded by ingestion (scrape error,
CAPTCHA, cleaner rejection); a missing scheme; a scheme with < 5 chunks; no Key Facts chunk;
a core field (expense ratio, exit load, minimum SIP, benchmark, riskometer) not found; a chunk
without source_url / scrape_date, with a stale scrape_date or from another run; duplicate
chunk IDs; a ChromaDB count that does not match the corpus; or failing Phase 6 tests run
against this index.

WARNS (job summary only) when a core value changed vs the previous snapshot or a chunk count
moved by more than 30%. Expected daily movers such as AUM are listed, never warned on.

Writes data/validation_staging.json; scripts/publish_snapshot.py refuses to publish without
a passing marker for the same build.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
if __name__ == "__main__":
    os.chdir(ROOT)

from app.ingestion import snapshot
from app.ingestion.quality import compare_with_previous, load_expected_schemes, validate_corpus

PHASE6_TESTS = "tests/test_phase6_integration.py"


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _git_show_json(ref: str, path: str):
    try:
        out = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, check=True)
        return json.loads(out.stdout.decode("utf-8"))
    except Exception:
        return None


def check_chroma(chroma_path: str, collection: str, expected: int, required: bool) -> list:
    """Errors if the ChromaDB collection is missing (when required) or its count differs."""
    if not os.path.isdir(chroma_path):
        return [f"ChromaDB directory `{chroma_path}` not found."] if required else []
    from app.ingestion.chroma_store import CHROMADB_AVAILABLE

    if not CHROMADB_AVAILABLE:
        return ["chromadb is not installed, so the ChromaDB store cannot be verified."] if required else []
    import chromadb

    try:
        client = chromadb.PersistentClient(path=chroma_path)
        count = client.get_collection(collection).count()
    except Exception as e:
        return [f"ChromaDB collection `{collection}` unreadable: {e}"]
    if count != expected:
        return [f"ChromaDB collection `{collection}` has {count} chunks, corpus has {expected}."]
    return []


def run_phase6_tests(vectorstore_dir: str, metadata_path: str):
    """Runs the Phase 6 suite against `vectorstore_dir`. Returns (passed, output tail)."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "VECTORSTORE_PATH": vectorstore_dir,
            "DATA_METADATA_PATH": metadata_path,
            "VECTOR_DB_PROVIDER": "local",  # the retrieval path the app serves by default
            "CHAT_DB_PATH": os.path.join(tmp, "chat.db"),
            "RUN_LIVE_EVAL": "0",
            "PYTHONPATH": ROOT,
        }
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", PHASE6_TESTS, "-q", "-p", "no:cacheprovider", "--no-header", "-rfE"],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
    output = (proc.stdout + proc.stderr).strip().splitlines()
    return proc.returncode == 0, "\n".join(output[-40:])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--staging", action="store_true", help="validate the staging build (default paths)")
    p.add_argument("--vectorstore", help="vectorstore dir (default: staging or live)")
    p.add_argument("--metadata", help="run metadata JSON (default: staging or live)")
    p.add_argument("--chroma-path")
    p.add_argument("--chroma-collection")
    p.add_argument("--urls", default="data/urls.json")
    p.add_argument("--previous", default="", help="git ref of the previous snapshot, e.g. origin/data-snapshot")
    p.add_argument("--require-today", action="store_true", help="scrape_date must be today's IST date")
    p.add_argument("--require-chroma", action="store_true", help="fail if the ChromaDB store is missing")
    p.add_argument("--skip-tests", action="store_true", help="do not run the Phase 6 regression tests")
    p.add_argument("--summary", default="", help="markdown file to append the report to")
    p.add_argument("--marker", default="", help="where to write the pass/fail marker")
    args = p.parse_args(argv)

    if args.staging:
        vectorstore = args.vectorstore or snapshot.STAGING_VECTORSTORE_PATH
        metadata_path = args.metadata or snapshot.STAGING_METADATA_PATH
        chroma_path = args.chroma_path or snapshot.STAGING_CHROMA_PATH
        collection = args.chroma_collection or snapshot.STAGING_COLLECTION
        marker = args.marker or snapshot.VALIDATION_MARKER_PATH
    else:
        from app.config import settings

        vectorstore = args.vectorstore or settings.vectorstore_path
        metadata_path = args.metadata or settings.data_metadata_path
        chroma_path = args.chroma_path or settings.chroma_db_path
        collection = args.chroma_collection or settings.vectorstore_collection
        marker = args.marker

    corpus = _load_json(os.path.join(vectorstore, "corpus.json")) or []
    metadata = _load_json(metadata_path)
    expected = load_expected_schemes(args.urls)
    run_id = (metadata or {}).get("run_id")
    expected_date = snapshot.ist_today() if args.require_today else None

    result = validate_corpus(corpus, metadata, expected, expected_date=expected_date, expected_run_id=run_id)
    if corpus:
        result.errors += check_chroma(chroma_path, collection, len(corpus), args.require_chroma)

    previous_corpus = None
    if args.previous:
        previous_corpus = _git_show_json(args.previous, "data/vectorstore/corpus.json")
        if previous_corpus is None:
            result.info.append(f"No previous snapshot at `{args.previous}` (first run?) — diff skipped.")
    diff_warnings, diff_rows = compare_with_previous(corpus, previous_corpus) if corpus else ([], [])
    result.warnings += diff_warnings

    test_output = ""
    if args.skip_tests:
        result.info.append("Phase 6 tests skipped (--skip-tests).")
    elif result.errors:
        result.info.append("Phase 6 tests not run: earlier checks already failed.")
    else:
        passed, test_output = run_phase6_tests(vectorstore, metadata_path)
        if not passed:
            result.errors.append(f"Phase 6 regression tests failed against `{vectorstore}`.")

    # ---- report ----
    status = "✅ PASSED" if result.passed else "❌ FAILED"
    md = [f"## 🛡️ Validation gate — {status}",
          f"Index `{vectorstore}` · {len(corpus)} chunks · run `{run_id}` · scrape date "
          f"`{(metadata or {}).get('scrape_date')}`"]
    if result.errors:
        md.append("**Blocking errors**\n\n" + "\n".join(f"- {e}" for e in result.errors))
    if result.warnings:
        md.append("**Warnings**\n\n" + "\n".join(f"- ⚠️ {w}" for w in result.warnings))
    if result.info:
        md.append("\n".join(f"- {i}" for i in result.info))
    if diff_rows:
        md.append("**Core facts vs previous snapshot**\n\n" + snapshot.md_table(
            ["Scheme", "Field", "Previous", "Current", ""],
            [[r["scheme_id"], r["label"], r["previous"], r["current"],
              ("changed (expected)" if r["expected"] else "⚠️ changed") if r["changed"] else ""]
             for r in diff_rows],
        ))
    if test_output:
        md.append("<details><summary>Phase 6 test output</summary>\n\n```\n" + test_output + "\n```\n</details>")
    report = "\n\n".join(md)
    print(report)
    snapshot.append_summary(args.summary, report)

    if marker:
        snapshot.write_json_atomic(marker, {
            "passed": result.passed,
            "generated_at": (metadata or {}).get("generated_at"),
            "run_id": run_id,
            "validated_at": snapshot.ist_now().isoformat(timespec="seconds"),
            "errors": result.errors,
            "warnings": result.warnings,
        })
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
