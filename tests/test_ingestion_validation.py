"""Phase 7.5 / 7.7 — validation gate rules and idempotent re-ingestion."""

import copy

import pytest

from app.config import settings
from app.ingestion.chunker import DocumentChunker, make_chunk_id
from app.ingestion.cleaner import clean
from app.ingestion.indexer import VectorIndexer
from app.ingestion.normalizer import normalize
from app.ingestion.quality import compare_with_previous, extract_facts, load_expected_schemes, validate_corpus
from app.ingestion.scraper import ScrapedDocument

RUN_DATE = "2026-11-21"
RUN_ID = "42"
EXPECTED = load_expected_schemes("data/urls.json")


def key_facts_text(name, ter="0.60%"):
    return (
        f"[{name} - Key Facts & Fund Parameters]\n{name} Key Facts: - Expense Ratio: {ter} "
        "- Exit Load: Exit load of 1% if redeemed within 1 year. "
        "- Benchmark: NIFTY Midcap 150 Total Return Index Scheme Information Document(SID) "
        "Min. for SIP ₹100 Fund size (AUM) ₹1,01,856 Cr Very High risk"
    )


def make_corpus(chunks_per_scheme=6, ter="0.60%"):
    corpus = []
    for scheme_id, url in EXPECTED.items():
        name = scheme_id.replace("-", " ").title()
        for i in range(chunks_per_scheme):
            heading = "Key Facts & Fund Parameters" if i == 0 else "Fund Management & Objective"
            text = key_facts_text(name, ter) if i == 0 else f"[{name} - {heading}]\nParagraph {i} about the fund."
            corpus.append({
                "chunk_id": make_chunk_id(url, heading, i), "scheme_id": scheme_id, "scheme_name": name,
                "category": "Equity", "source_url": url, "document_type": "groww", "section_heading": heading,
                "scrape_date": RUN_DATE, "text": text, "run_id": RUN_ID,
            })
    return corpus


def make_metadata(corpus):
    return {"total_chunks": len(corpus), "scrape_date": RUN_DATE, "run_id": RUN_ID, "failures": []}


def run_gate(corpus, metadata=None):
    metadata = make_metadata(corpus) if metadata is None else metadata
    return validate_corpus(corpus, metadata, EXPECTED, expected_date=RUN_DATE, expected_run_id=RUN_ID)


# ------------------------------------------------------------------------------
# Gate: passes on a good build
# ------------------------------------------------------------------------------
def test_gate_passes_on_good_fixture():
    result = run_gate(make_corpus())
    assert result.passed, result.errors
    assert result.warnings == []


def test_core_facts_extracted():
    facts = extract_facts(make_corpus())["hdfc-mid-cap"]
    assert facts == {
        "expense_ratio": "0.60%", "exit_load": "1% if redeemed within 1 year", "min_sip": "100",
        "benchmark": "NIFTY Midcap 150 Total Return Index", "riskometer": "Very High", "aum": "1,01,856 Cr",
    }


# ------------------------------------------------------------------------------
# Gate: blocking failures
# ------------------------------------------------------------------------------
def test_gate_fails_on_missing_scheme():
    corpus = [c for c in make_corpus() if c["scheme_id"] != "hdfc-small-cap"]
    result = run_gate(corpus)
    assert not result.passed
    assert any("hdfc-small-cap" in e and "missing" in e for e in result.errors)


def test_gate_fails_on_missing_key_facts():
    corpus = make_corpus()
    for c in corpus:
        if c["scheme_id"] == "hdfc-mid-cap":
            c["section_heading"] = "Fund Management & Objective"
    result = run_gate(corpus)
    assert any("hdfc-mid-cap" in e and "Key Facts" in e for e in result.errors)


def test_gate_fails_on_stale_scrape_date():
    corpus = make_corpus()
    corpus[3]["scrape_date"] = "2026-10-25"
    result = run_gate(corpus)
    assert any("stale scrape_date" in e for e in result.errors)


def test_gate_fails_on_missing_source_url_or_date():
    corpus = make_corpus()
    corpus[1]["source_url"] = ""
    corpus[2]["scrape_date"] = ""
    errors = " ".join(run_gate(corpus).errors)
    assert "no source_url" in errors and "no scrape_date" in errors


def test_gate_fails_on_too_few_chunks():
    corpus = make_corpus(chunks_per_scheme=4)
    result = run_gate(corpus)
    assert sum("(< 5)" in e for e in result.errors) == len(EXPECTED)


def test_gate_fails_on_missing_core_field():
    corpus = make_corpus()
    for c in corpus:
        if c["scheme_id"] == "hdfc-multi-cap":
            c["text"] = c["text"].replace("Benchmark", "Index")
    result = run_gate(corpus)
    assert any("hdfc-multi-cap" in e and "Benchmark" in e for e in result.errors)


def test_gate_fails_on_recorded_captcha_page():
    corpus = make_corpus()
    meta = make_metadata(corpus)
    meta["failures"] = [{"scheme_id": "hdfc-mid-cap", "stage": "scrape",
                         "error": "BlockedPageError: Bot-block / CAPTCHA page detected"}]
    result = run_gate(corpus, meta)
    assert any("CAPTCHA" in e for e in result.errors)


def test_gate_fails_on_duplicates_and_other_runs():
    corpus = make_corpus()
    corpus.append(copy.deepcopy(corpus[0]))
    corpus[5]["run_id"] = "41"
    errors = " ".join(run_gate(corpus).errors)
    assert "duplicate chunk IDs" in errors
    assert "not from run 42" in errors


def test_gate_fails_on_foreign_citation():
    corpus = make_corpus()
    corpus[0]["source_url"] = "https://example.com/other-fund"
    assert any("outside data/urls.json" in e for e in run_gate(corpus).errors)


def test_gate_fails_without_metadata():
    result = validate_corpus(make_corpus(), None, EXPECTED)
    assert any("metadata" in e.lower() for e in result.errors)


# ------------------------------------------------------------------------------
# Warnings vs the previous snapshot (never blocking)
# ------------------------------------------------------------------------------
def test_no_warnings_when_unchanged():
    warnings, rows = compare_with_previous(make_corpus(), make_corpus())
    assert warnings == []
    assert not any(r["changed"] for r in rows)


def test_warns_on_core_value_change_but_not_on_aum():
    previous = make_corpus()
    current = make_corpus(ter="0.74%")
    for c in current:
        c["text"] = c["text"].replace("₹1,01,856", "₹1,02,000")
    warnings, rows = compare_with_previous(current, previous)
    assert len([w for w in warnings if "Expense ratio" in w]) == len(EXPECTED)
    assert not any("AUM" in w for w in warnings)
    assert any(r["field"] == "aum" and r["changed"] and r["expected"] for r in rows)


def test_warns_on_large_chunk_count_change():
    warnings, _ = compare_with_previous(make_corpus(chunks_per_scheme=10), make_corpus(chunks_per_scheme=6))
    assert any("Total chunk count" in w for w in warnings)


def test_first_run_has_no_previous():
    warnings, rows = compare_with_previous(make_corpus(), None)
    assert warnings == [] and rows and all(r["previous"] is None for r in rows)


# ------------------------------------------------------------------------------
# Idempotent re-ingestion (7.5, edge-cases.md §7.10)
# ------------------------------------------------------------------------------
def scraped_fixture():
    long_para = "The scheme invests predominantly in mid cap companies with a long-term horizon. " * 12
    return ScrapedDocument(
        scheme_id="hdfc-mid-cap", scheme_name="HDFC Mid-Cap Opportunities Fund", category="Mid Cap Fund",
        url=EXPECTED["hdfc-mid-cap"], amc="HDFC Mutual Fund", scrape_date=RUN_DATE, full_text="",
        sections=[
            {"section": "Scheme Overview", "text": "Scheme Name: HDFC Mid-Cap Opportunities Fund. Category: Mid Cap Fund."},
            {"section": "Key Facts & Fund Parameters", "text": "HDFC Mid-Cap Key Facts:\n- TER: 0.60 %\n- Exit load: 1%"},
            {"section": "Fund Management & Objective", "text": "About the fund:\n" + long_para},
        ],
    )


def build_chunks(run_id):
    doc = clean(normalize(scraped_fixture()))
    return DocumentChunker(chunk_size=300, chunk_overlap=50, run_id=run_id).chunk_documents([doc])


def test_reingesting_same_page_yields_identical_ids():
    first, second = build_chunks("1"), build_chunks("2")
    ids = [c.chunk_id for c in first]
    assert ids == [c.chunk_id for c in second]  # run_id does not affect identity
    assert len(ids) == len(set(ids)) and len(ids) > 3
    assert all(len(i) == 40 for i in ids)  # sha1 hex
    assert [c.text for c in first] == [c.text for c in second]
    assert {c.run_id for c in second} == {"2"}


def test_reindexing_twice_has_no_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "vector_db_provider", "local")
    indexer = VectorIndexer(vectorstore_dir=str(tmp_path))
    indexer.index_chunks(build_chunks("1"))
    catalog = indexer.index_chunks(build_chunks("2"))
    reloaded = VectorIndexer(vectorstore_dir=str(tmp_path))
    assert reloaded.load()
    ids = [c["chunk_id"] for c in reloaded.chunks]
    assert len(ids) == len(set(ids)) == catalog["total_chunks"]
    assert {c["run_id"] for c in reloaded.chunks} == {"2"}


def test_indexer_refuses_duplicate_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "vector_db_provider", "local")
    chunks = build_chunks("1")
    with pytest.raises(ValueError, match="Duplicate chunk IDs"):
        VectorIndexer(vectorstore_dir=str(tmp_path)).index_chunks(chunks + chunks[:1])


def test_chroma_sync_upserts_and_deletes_stale(tmp_path):
    pytest.importorskip("chromadb")
    from app.ingestion.chroma_store import ChromaVectorStore

    store = ChromaVectorStore(persist_directory=str(tmp_path / "chroma"), collection_name="t_sync")
    assert store.is_ready()
    chunks = [c.to_dict() for c in build_chunks("1")]
    dim4 = [[1.0, 0.0, 0.0, float(i)] for i in range(len(chunks))]

    store.sync_chunks(chunks, dim4)
    store.sync_chunks(chunks, dim4)  # same run again: no duplicates
    assert store.count() == len(chunks)

    fewer = chunks[:-1]
    stats = store.sync_chunks(fewer, [[1.0, 0.0, 0.0, 0.0, float(i)] for i in range(len(fewer))])
    assert store.count() == len(fewer)  # stale chunk removed
    assert stats["reset"] == 1  # vocabulary (dimension) changed -> collection recreated
