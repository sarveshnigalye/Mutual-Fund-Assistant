"""Phase 6 evaluation runner (implementation-plan.md §6.2–6.7).

Runs every query in tests/test_queries.json through the REAL pipeline (Groq + local index),
checks each acceptance criterion, measures latency, audits citations, verifies thread isolation,
and writes:
  - Docs/phase6-test-report.md   (human-readable results log, citation audit, latency report)
  - data/phase6_results.json     (raw per-query results)

Usage:  python scripts/run_phase6_eval.py
"""

import json
import os
import re
import statistics
import sys
import tempfile
import time
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.chat.manager import ChatThreadManager  # noqa: E402
from app.config import settings  # noqa: E402
from app.core.formatter import split_sentences  # noqa: E402
from app.core.rag_pipeline import rag_pipeline  # noqa: E402

FOOTER_RE = re.compile(r"_Last updated from sources: \d{4}-\d{2}-\d{2}_$")
URL_RE = re.compile(r"https?://\S+")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
AMC_URL = "https://www.hdfcfund.com"
LATENCY_TARGET_S = 5.0


def load_json(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def split_response(response):
    body, _, rest = response.partition("\n\n📎 Source: ")
    citation, _, footer = rest.partition("\n\n")
    return body.strip(), citation.strip(), footer.strip()


def evaluate(q, res, corpus_urls):
    checks = {}
    text = res.response
    expected = q.get("expected_category")
    if expected:
        checks["category"] = res.category == expected

    if res.is_refusal:
        if q.get("expected_link"):
            checks["refusal_link"] = q["expected_link"] in text
        checks["no_factual_leakage"] = (
            not res.retrieved_chunks and res.source_url is None and "📎 Source:" not in text
        )
        if q.get("expected_text"):
            checks["expected_text"] = q["expected_text"] in text
        return checks

    body, citation, footer = split_response(text)
    checks["<=3_sentences"] = len(split_sentences(body)) <= 3
    checks["one_citation"] = text.count("📎 Source:") == 1 and not URL_RE.search(body)
    checks["citation_valid"] = citation in corpus_urls | {AMC_URL} and citation == res.source_url
    checks["footer"] = bool(FOOTER_RE.match(footer))
    if q.get("expected_source"):
        checks["expected_source"] = res.source_url == q["expected_source"]
    if q.get("expected_text"):
        checks["expected_text"] = q["expected_text"] in text
    if q.get("expect_truncated"):
        checks["truncated"] = res.truncated
    if res.source_url in corpus_urls:
        src_text = " ".join(
            c["text"] for c in res.retrieved_chunks if c.get("source_url") == res.source_url
        ).replace(",", "")
        missing = [n for n in NUM_RE.findall(body.replace(",", "")) if n not in src_text]
        checks["traceable_to_source"] = not missing
        if missing:
            checks["_untraceable_numbers"] = missing
    return checks


def thread_isolation_check():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = ChatThreadManager(db_path=os.path.join(tmp, "iso.db"))
        threads = [mgr.create_thread(f"T{i}") for i in range(3)]
        for i, t in enumerate(threads):
            mgr.add_message(t.thread_id, "user", f"q{i}")
            mgr.add_message(t.thread_id, "assistant", f"a{i}")
        isolated = all(
            [m.content for m in mgr.get_thread_history(t.thread_id)] == [f"q{i}", f"a{i}"]
            for i, t in enumerate(threads)
        )
        mgr.delete_thread(threads[1].thread_id)
        survivors_ok = all(
            mgr.get_thread(threads[i].thread_id).message_count == 2 for i in (0, 2)
        )
        deleted_gone = mgr.get_thread(threads[1].thread_id) is None
        return isolated and survivors_ok and deleted_gone


def main():
    queries = load_json("tests", "test_queries.json")
    corpus_urls = {u["url"] for u in load_json("data", "urls.json")}
    live = bool(settings.groq_api_key)
    if not live:
        print("WARNING: GROQ_API_KEY not set — generation will return fallbacks; results are not a real eval.")

    rows = []
    for q in queries:
        text = q["query"] * q.get("repeat", 1)
        start = time.perf_counter()
        try:
            res = rag_pipeline.run(text)
            error = None
        except Exception as e:  # report, don't abort the run
            res, error = None, repr(e)
        elapsed = time.perf_counter() - start

        checks = {"no_exception": error is None}
        if res is not None:
            checks.update(evaluate(q, res, corpus_urls))
        passed = all(v for k, v in checks.items() if not k.startswith("_"))
        rows.append({
            "id": q["id"], "group": q["group"], "query": text[:120],
            "expected_category": q.get("expected_category"),
            "category": res.category if res else None,
            "is_refusal": res.is_refusal if res else None,
            "source_url": res.source_url if res else None,
            "response": res.response if res else error,
            "latency_s": round(elapsed, 3),
            "checks": checks, "passed": passed,
        })
        print(f"[{'PASS' if passed else 'FAIL'}] {q['id']:<4} {elapsed:5.2f}s  {text[:70]!r}")

    isolation_ok = thread_isolation_check()

    # Aggregates mapped to the Phase 6 acceptance criteria
    factual = [r for r in rows if r["group"] == "factual"]
    refusals = [r for r in rows if r["group"] == "refusal"]
    answered = [r for r in rows if r["is_refusal"] is False]
    llm_rows = [r for r in rows if r["group"] == "factual"][:10]
    latencies = [r["latency_s"] for r in llm_rows]

    def pct(xs):
        return 100.0 * sum(xs) / len(xs) if xs else 0.0

    criteria = [
        ("≥90% of factual queries accurate & correctly formatted", pct([r["passed"] for r in factual]), 90.0),
        ("100% of advisory/PII/OOS queries correctly refused", pct([r["passed"] for r in refusals]), 100.0),
        ("100% of answers carry exactly one valid citation + footer",
         pct([r["checks"].get("one_citation", False) and r["checks"].get("citation_valid", False)
              and r["checks"].get("footer", False) for r in answered]), 100.0),
        ("All answers ≤ 3 sentences", pct([r["checks"].get("<=3_sentences", False) for r in answered]), 100.0),
        ("Multi-thread isolation confirmed", 100.0 if isolation_ok else 0.0, 100.0),
    ]
    avg_latency = statistics.mean(latencies) if latencies else 0.0

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "phase6_results.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(), "live_llm": live, "rows": rows}, f, indent=2, ensure_ascii=False)

    lines = [
        "# Phase 6 — Integration & End-to-End Test Report",
        "",
        f"_Generated: {datetime.now():%Y-%m-%d %H:%M} · LLM: `{settings.groq_model}` · "
        f"Live LLM: {'yes' if live else 'NO (fallback only — not a valid accuracy run)'}_",
        "",
        "## Acceptance criteria",
        "",
        "| Criterion | Result | Target | Status |",
        "| :--- | ---: | ---: | :---: |",
    ]
    for name, value, target in criteria:
        lines.append(f"| {name} | {value:.0f}% | {target:.0f}% | {'✅' if value >= target else '❌'} |")
    lines.append(
        f"| Average latency (10 factual queries) | {avg_latency:.2f}s | ≤ {LATENCY_TARGET_S:.0f}s | "
        f"{'✅' if latencies and avg_latency <= LATENCY_TARGET_S else '❌'} |"
    )

    lines += ["", "## Results log", "", "| ID | Group | Expected | Got | Latency | Result | Failed checks |",
              "| :--- | :--- | :--- | :--- | ---: | :---: | :--- |"]
    for r in rows:
        failed = ", ".join(k for k, v in r["checks"].items() if not k.startswith("_") and not v)
        extra = r["checks"].get("_untraceable_numbers")
        if extra:
            failed += f" (untraceable: {', '.join(extra)})"
        lines.append(
            f"| {r['id']} | {r['group']} | {r['expected_category'] or '—'} | {r['category'] or 'error'} | "
            f"{r['latency_s']:.2f}s | {'✅' if r['passed'] else '❌'} | {failed or '—'} |"
        )

    lines += ["", "## Citation audit (§6.5)", "", "| ID | Cited source | In `data/urls.json` | Numbers traceable |",
              "| :--- | :--- | :---: | :---: |"]
    for r in answered:
        src = r["source_url"] or "—"
        lines.append(
            f"| {r['id']} | {src} | {'✅' if src in corpus_urls else ('AMC fallback' if src == AMC_URL else '❌')} | "
            f"{'✅' if r['checks'].get('traceable_to_source', src == AMC_URL) else '❌'} |"
        )

    if latencies:
        lines += [
            "", "## Latency report (§6.7)", "",
            f"- Queries measured: {len(latencies)} factual (full pipeline incl. Groq call)",
            f"- Mean {statistics.mean(latencies):.2f}s · median {statistics.median(latencies):.2f}s · "
            f"max {max(latencies):.2f}s · min {min(latencies):.2f}s",
            "- Refusals return before retrieval/LLM, so their latency reflects classifier cost only "
            "(Layer 2 LLM is used only for queries Layer 1 cannot decide).",
        ]

    lines += ["", "## Responses", ""]
    for r in rows:
        lines += [f"**{r['id']}** — `{r['query']}`", "", "```", (r["response"] or "").strip(), "```", ""]

    report_path = os.path.join(ROOT, "Docs", "phase6-test-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nThread isolation: {'OK' if isolation_ok else 'FAILED'}")
    print(f"Average latency (factual): {avg_latency:.2f}s")
    print(f"Report written to {report_path}")
    return 0 if all(v >= t for _, v, t in criteria) else 1


if __name__ == "__main__":
    sys.exit(main())
