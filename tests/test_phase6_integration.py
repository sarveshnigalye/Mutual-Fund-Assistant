"""Phase 6 — Integration & end-to-end tests (implementation-plan.md §6.1–6.7).

Two modes:
- Offline (default): real preprocessing, classifier Layer 1, retriever (local TF-IDF/BM25 index),
  formatter, chat manager and API — with the Groq calls replaced by an extractive stand-in that
  answers from the top retrieved chunk. Deterministic; needs no network.
- Live (RUN_LIVE_EVAL=1 and GROQ_API_KEY set): runs the real pipeline end-to-end for factual
  accuracy (6.2) and latency (6.7). `scripts/run_phase6_eval.py` produces the full written report.
"""

import json
import os
import re
import statistics
import time

import pytest
from fastapi.testclient import TestClient

from app.chat.manager import ChatThreadManager
from app.core.classifier import QueryCategory, QueryClassifier
from app.core.formatter import split_sentences
from app.core.rag_pipeline import RAGPipeline
from app.core.retriever import MutualFundRetriever

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
with open(os.path.join(ROOT, "tests", "test_queries.json"), encoding="utf-8") as f:
    QUERIES = json.load(f)
with open(os.path.join(ROOT, "data", "urls.json"), encoding="utf-8") as f:
    CORPUS_URLS = {u["url"] for u in json.load(f)}
AMC_FALLBACK_URL = "https://www.hdfcfund.com"
ALLOWED_CITATIONS = CORPUS_URLS | {AMC_FALLBACK_URL}

LIVE = os.getenv("RUN_LIVE_EVAL") == "1" and bool(os.getenv("GROQ_API_KEY"))

FOOTER_RE = re.compile(r"_Last updated from sources: \d{4}-\d{2}-\d{2}_$")
URL_RE = re.compile(r"https?://\S+")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")


# ------------------------------------------------------------------------------
# Helpers & fixtures
# ------------------------------------------------------------------------------
def query_text(q: dict) -> str:
    return q["query"] * q.get("repeat", 1)


def group(name: str):
    return [q for q in QUERIES if q["group"] == name]


def ids(qs):
    return [q["id"] for q in qs]


def split_response(response: str):
    """Returns (body, citation_url, footer) of a formatted factual response."""
    body, _, rest = response.partition("\n\n📎 Source: ")
    citation, _, footer = rest.partition("\n\n")
    return body.strip(), citation.strip(), footer.strip()


def untraceable_numbers(body: str, chunks: list, source_url: str) -> list:
    """Numbers in the answer that do not appear in any retrieved chunk from the cited source."""
    source_text = " ".join(c["text"] for c in chunks if c.get("source_url") == source_url).replace(",", "")
    return [n for n in NUM_RE.findall(body.replace(",", "")) if n not in source_text]


class ExtractiveGenerator:
    """Offline stand-in for the Groq generator: answers with the top chunk's own sentences."""

    def generate(self, query, chunks):
        lines = [ln.strip() for ln in chunks[0]["text"].splitlines() if ln.strip()]
        body = [ln for ln in lines if not ln.startswith("[")] or lines
        return " ".join(body)


@pytest.fixture(scope="module")
def offline_classifier():
    clf = QueryClassifier()
    clf.client = None  # never call Groq; inconclusive -> FACTUAL (documented Layer 2 default)
    return clf


@pytest.fixture(scope="module")
def retriever():
    r = MutualFundRetriever()
    if not r.load():
        pytest.skip("Vector index not found — run scripts/ingest.py first.")
    return r


@pytest.fixture(scope="module")
def pipeline(retriever, offline_classifier):
    return RAGPipeline(retriever=retriever, generator=ExtractiveGenerator(), classifier=offline_classifier)


@pytest.fixture()
def temp_manager(tmp_path):
    return ChatThreadManager(db_path=str(tmp_path / "chat_test.db"))


# ------------------------------------------------------------------------------
# 6.1 Test query suite
# ------------------------------------------------------------------------------
def test_6_1_query_suite_coverage():
    assert len(QUERIES) >= 30
    assert len(group("factual")) >= 10
    assert len(group("refusal")) >= 10
    assert len({q["id"] for q in QUERIES}) == len(QUERIES), "duplicate query ids"
    refusal_categories = {q["expected_category"] for q in group("refusal")}
    assert {"ADVISORY", "COMPARATIVE", "PERFORMANCE", "PII_DETECTED", "OUT_OF_SCOPE"} <= refusal_categories
    cases = " ".join(q["case"] for q in group("edge")).lower()
    for required in ("empty", "long", "hindi", "special", "non-indexed", "borderline"):
        assert required in cases, f"edge case '{required}' missing from suite"


@pytest.mark.parametrize("q", [q for q in QUERIES if q.get("expected_category")], ids=lambda q: q["id"])
def test_6_1_classification_matrix(pipeline, q):
    res = pipeline.run(query_text(q))
    assert res.category == q["expected_category"], f"{q['id']}: {q['query'][:60]!r}"


# ------------------------------------------------------------------------------
# 6.2 Factual responses: format compliance (offline) — accuracy is checked live below
# ------------------------------------------------------------------------------
FACTUAL_CASES = [q for q in QUERIES if q.get("expected_category") == "FACTUAL"]


@pytest.mark.parametrize("q", FACTUAL_CASES, ids=lambda q: q["id"])
def test_6_2_factual_format_compliance(pipeline, q):
    res = pipeline.run(query_text(q))
    assert res.is_refusal is False
    body, citation, footer = split_response(res.response)

    assert body, "empty answer body"
    assert len(split_sentences(body)) <= 3, f"more than 3 sentences: {body!r}"
    assert res.response.count("📎 Source:") == 1, "must carry exactly one citation line"
    assert not URL_RE.search(body), f"URL leaked into answer body: {body!r}"
    assert citation == res.source_url
    assert citation in ALLOWED_CITATIONS
    assert FOOTER_RE.match(footer), f"bad footer: {footer!r}"
    if q.get("expected_source"):
        assert res.source_url == q["expected_source"]
    if q.get("expected_text"):
        assert q["expected_text"] in res.response


# ------------------------------------------------------------------------------
# 6.3 Refusals
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("q", group("refusal"), ids=lambda q: q["id"])
def test_6_3_refusals(pipeline, offline_classifier, q):
    text = query_text(q)
    res = pipeline.run(text)
    assert res.is_refusal is True
    assert res.category == q["expected_category"]
    assert q["expected_link"] in res.response, "educational / redirect link missing"
    # No factual leakage: exactly the approved template, no retrieval, no citation, no footer
    expected = offline_classifier.get_refusal(QueryCategory(q["expected_category"]), text)
    assert res.response == expected
    assert res.retrieved_chunks == []
    assert res.source_url is None
    assert "📎 Source:" not in res.response and "Last updated from sources" not in res.response


# ------------------------------------------------------------------------------
# 6.4 Edge cases
# ------------------------------------------------------------------------------
EDGE = {q["id"]: q for q in group("edge")}


def test_6_4_empty_query_rejected_by_api():
    from app.main import app

    client = TestClient(app)
    assert client.post("/api/chat", json={"query": ""}).status_code in (400, 422)
    assert client.post("/api/chat", json={"query": "   "}).status_code == 400


def test_6_4_empty_and_short_queries_get_friendly_prompt(pipeline):
    for qid in ("E01", "E02"):
        res = pipeline.run(query_text(EDGE[qid]))
        assert res.is_refusal and res.category == "INVALID_INPUT"
        assert "Please enter a question" in res.response


def test_6_4_long_query_truncated(pipeline):
    q = EDGE["E03"]
    text = query_text(q)
    assert len(text) > 500
    res = pipeline.run(text)
    assert res.truncated is True
    assert res.category == "FACTUAL"
    assert res.query == text  # the stored query is the user's original text


def test_6_4_hindi_query(pipeline):
    res = pipeline.run(EDGE["E04"]["query"])
    assert res.is_refusal and res.category == "OUT_OF_SCOPE"
    assert "English queries only" in res.response


def test_6_4_special_chars_and_html_are_sanitised(pipeline):
    for qid in ("E05", "E06"):
        res = pipeline.run(EDGE[qid]["query"])
        assert res.category == "FACTUAL"
        assert res.source_url == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
        assert "<script" not in res.response and "alert(" not in res.response


def test_6_4_non_indexed_scheme(pipeline):
    res = pipeline.run(EDGE["E07"]["query"])
    assert "I don't have verified information on this" in res.response
    assert res.source_url == AMC_FALLBACK_URL
    assert res.retrieved_chunks == []


def test_6_4_borderline_query_is_answered(pipeline):
    res = pipeline.run(EDGE["E08"]["query"])
    assert res.category == "FACTUAL" and not res.is_refusal


def test_6_4_sql_injection_string_is_harmless(pipeline, temp_manager):
    text = EDGE["E09"]["query"]
    res = pipeline.run(text)  # must not raise
    t = temp_manager.create_thread("injection")
    temp_manager.add_message(t.thread_id, "user", text)
    temp_manager.add_message(t.thread_id, "assistant", res.response, source_url=res.source_url)
    history = temp_manager.get_thread_history(t.thread_id)
    assert [m.content for m in history][0] == text  # stored verbatim via parameterised SQL
    assert len(temp_manager.list_threads()) == 1


def test_6_4_company_word_no_longer_flagged_as_pan(pipeline):
    res = pipeline.run(EDGE["E11"]["query"])
    assert res.category == "FACTUAL"


# ------------------------------------------------------------------------------
# 6.5 Citation validation
# ------------------------------------------------------------------------------
TRACEABLE = [q for q in group("factual") if q.get("expected_source")]


@pytest.mark.parametrize("q", TRACEABLE, ids=lambda q: q["id"])
def test_6_5_citation_traceable_to_source_chunk(pipeline, q):
    res = pipeline.run(query_text(q))
    assert res.source_url in CORPUS_URLS
    assert res.retrieved_chunks, "factual answer without retrieved context"
    assert res.retrieved_chunks[0]["source_url"] == res.source_url, "citation is not the top chunk's source"
    body, _, _ = split_response(res.response)
    missing = untraceable_numbers(body, res.retrieved_chunks, res.source_url)
    assert not missing, f"numbers not traceable to cited source: {missing}"


# ------------------------------------------------------------------------------
# 6.6 Multi-thread isolation
# ------------------------------------------------------------------------------
def test_6_6_thread_isolation_manager(temp_manager):
    threads = [temp_manager.create_thread(f"T{i}") for i in range(3)]
    for i, t in enumerate(threads):
        temp_manager.add_message(t.thread_id, "user", f"question-{i}")
        temp_manager.add_message(t.thread_id, "assistant", f"answer-{i}")

    for i, t in enumerate(threads):
        contents = [m.content for m in temp_manager.get_thread_history(t.thread_id)]
        assert contents == [f"question-{i}", f"answer-{i}"]

    assert temp_manager.delete_thread(threads[1].thread_id)
    assert temp_manager.get_thread(threads[1].thread_id) is None
    with temp_manager._get_connection() as conn:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE thread_id = ?", (threads[1].thread_id,)
        ).fetchone()[0]
    assert orphans == 0, "messages of deleted thread were not cascaded"

    for i in (0, 2):
        t = temp_manager.get_thread(threads[i].thread_id)
        assert t.message_count == 2
        assert [m.content for m in t.messages] == [f"question-{i}", f"answer-{i}"]


def test_6_6_thread_isolation_via_api(monkeypatch, pipeline, temp_manager):
    import app.api.routes as routes
    from app.main import app

    monkeypatch.setattr(routes, "chat_manager", temp_manager)
    monkeypatch.setattr(routes, "rag_pipeline", pipeline)
    client = TestClient(app)

    queries = [
        "What is the expense ratio of HDFC Mid Cap Fund?",
        "Should I invest in HDFC Small Cap Fund?",
        "What is the benchmark index of HDFC Multi Cap Fund?",
    ]
    thread_ids = []
    for q in queries:
        tid = client.post("/api/threads", json={}).json()["thread_id"]
        r = client.post("/api/chat", json={"query": q, "thread_id": tid})
        assert r.status_code == 200 and r.json()["thread_id"] == tid
        thread_ids.append(tid)

    for tid, q in zip(thread_ids, queries):
        msgs = client.get(f"/api/threads/{tid}").json()["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[0]["content"] == q

    assert client.delete(f"/api/threads/{thread_ids[0]}").status_code == 200
    assert client.get(f"/api/threads/{thread_ids[0]}").status_code == 404
    remaining = {t["thread_id"] for t in client.get("/api/threads").json()}
    assert remaining == set(thread_ids[1:])
    for tid in thread_ids[1:]:
        assert len(client.get(f"/api/threads/{tid}").json()["messages"]) == 2


# ------------------------------------------------------------------------------
# 6.7 Latency
# ------------------------------------------------------------------------------
def test_6_7_offline_pipeline_overhead(pipeline):
    """Everything except the LLM call (preprocess, classify, retrieve, format) should be fast."""
    timings = []
    for q in group("factual")[:10]:
        start = time.perf_counter()
        pipeline.run(query_text(q))
        timings.append(time.perf_counter() - start)
    assert statistics.mean(timings) < 1.0, f"non-LLM overhead too high: {timings}"


# ------------------------------------------------------------------------------
# Live mode (real Groq): 6.2 accuracy + 6.7 latency
# ------------------------------------------------------------------------------
@pytest.mark.skipif(not LIVE, reason="Set RUN_LIVE_EVAL=1 and GROQ_API_KEY to run live LLM checks.")
def test_6_2_and_6_7_live_factual_accuracy_and_latency():
    from app.core.rag_pipeline import rag_pipeline

    results, timings = [], []
    for q in group("factual")[:10]:
        start = time.perf_counter()
        res = rag_pipeline.run(query_text(q))
        timings.append(time.perf_counter() - start)
        body, citation, footer = split_response(res.response)
        ok = (
            not res.is_refusal
            and len(split_sentences(body)) <= 3
            and citation in ALLOWED_CITATIONS
            and bool(FOOTER_RE.match(footer))
            and (res.source_url == AMC_FALLBACK_URL
                 or not untraceable_numbers(body, res.retrieved_chunks, res.source_url))
        )
        results.append(ok)

    assert sum(results) / len(results) >= 0.9, f"factual pass rate below 90%: {results}"
    assert statistics.mean(timings) <= 5.0, f"average latency above 5s: {timings}"
