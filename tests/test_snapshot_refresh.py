"""Phase 7.8–7.10 — snapshot promotion, app-side sync, hot reload and the footer date."""

import importlib.util
import json
import os
import shutil

import pytest

from app.config import settings
from app.core.formatter import format_response
from app.core.retriever import MutualFundRetriever
from app.ingestion import snapshot
from app.ingestion.chunker import DocumentChunk
from app.ingestion.indexer import VectorIndexer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"script_{name}", os.path.join(ROOT, "scripts", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def local_provider(monkeypatch):
    monkeypatch.setattr(settings, "vector_db_provider", "local")


def build_index(directory, ter):
    chunks = [
        DocumentChunk(
            chunk_id="mid-kf", scheme_id="hdfc-mid-cap", scheme_name="HDFC Mid-Cap Opportunities Fund",
            category="Mid Cap", source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
            document_type="groww", section_heading="Key Facts & Fund Parameters", scrape_date="2026-11-21",
            text=f"[HDFC Mid-Cap Opportunities Fund - Key Facts]\nExpense ratio is {ter}. Expense ratio covers fees.",
        ),
        DocumentChunk(
            chunk_id="small-exit", scheme_id="hdfc-small-cap", scheme_name="HDFC Small Cap Fund",
            category="Small Cap", source_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
            document_type="groww", section_heading="Exit Load", scrape_date="2026-11-21",
            text="[HDFC Small Cap Fund - Exit Load]\nExit load of 1% if redeemed within 1 year.",
        ),
    ]
    VectorIndexer(vectorstore_dir=str(directory)).index_chunks(chunks)


def top_text(retriever):
    return retriever.indexer.search("What is the expense ratio of HDFC Mid Cap?", top_k=1)[0]["text"]


# ------------------------------------------------------------------------------
# 7.9 (b) hot reload
# ------------------------------------------------------------------------------
def test_retriever_hot_reloads_new_snapshot(tmp_path):
    live, meta = tmp_path / "vectorstore", tmp_path / "metadata.json"
    build_index(live, "0.60%")
    snapshot.write_json_atomic(str(meta), {"generated_at": "v1", "scrape_date": "2026-11-20"})

    retriever = MutualFundRetriever(vectorstore_dir=str(live), metadata_path=str(meta), reload_check_seconds=0)
    assert retriever.load()
    assert retriever.snapshot_version == "v1"
    assert "0.60%" in top_text(retriever)

    build_index(tmp_path / "incoming", "0.74%")
    snapshot.replace_dir(str(tmp_path / "incoming"), str(live))
    snapshot.write_json_atomic(str(meta), {"generated_at": "v2", "scrape_date": "2026-11-21"})

    assert retriever.load()  # no restart: the next request picks it up
    assert retriever.snapshot_version == "v2"
    assert "0.74%" in top_text(retriever)


def test_reload_failure_keeps_serving_previous_index(tmp_path):
    live, meta = tmp_path / "vectorstore", tmp_path / "metadata.json"
    build_index(live, "0.60%")
    snapshot.write_json_atomic(str(meta), {"generated_at": "v1"})
    retriever = MutualFundRetriever(vectorstore_dir=str(live), metadata_path=str(meta), reload_check_seconds=0)
    assert retriever.load()

    shutil.rmtree(live)  # a broken / half-synced snapshot
    snapshot.write_json_atomic(str(meta), {"generated_at": "v2"})
    assert retriever.load()
    assert retriever.snapshot_version == "v1"
    assert "0.60%" in top_text(retriever)


def test_reload_check_is_throttled(tmp_path):
    live, meta = tmp_path / "vectorstore", tmp_path / "metadata.json"
    build_index(live, "0.60%")
    snapshot.write_json_atomic(str(meta), {"generated_at": "v1"})
    retriever = MutualFundRetriever(vectorstore_dir=str(live), metadata_path=str(meta), reload_check_seconds=3600)
    assert retriever.load()
    snapshot.write_json_atomic(str(meta), {"generated_at": "v2"})
    assert retriever.load()
    assert retriever.snapshot_version == "v1"  # not re-checked within the interval


# ------------------------------------------------------------------------------
# 7.9 (c) footer date
# ------------------------------------------------------------------------------
def test_footer_falls_back_to_snapshot_scrape_date(tmp_path, monkeypatch):
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps({"generated_at": "g", "scrape_date": "2030-01-02"}), encoding="utf-8")
    monkeypatch.setattr(settings, "data_metadata_path", str(meta))
    out = format_response("The expense ratio is 0.60%.", "https://groww.in/x", scrape_date=None)
    assert out.endswith("_Last updated from sources: 2030-01-02_")
    # an explicit chunk date still wins
    assert format_response("Ok.", "https://groww.in/x", scrape_date="2030-01-01").endswith("2030-01-01_")


def test_footer_without_any_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_metadata_path", str(tmp_path / "missing.json"))
    monkeypatch.setattr(settings, "vectorstore_path", str(tmp_path / "missing_dir"))
    assert format_response("Ok.", "https://groww.in/x").endswith(f"{snapshot.UNKNOWN_DATE}_")


# ------------------------------------------------------------------------------
# Atomic swap helpers
# ------------------------------------------------------------------------------
def test_replace_dir_swaps_and_cleans_up(tmp_path):
    (tmp_path / "live").mkdir()
    (tmp_path / "live" / "old.txt").write_text("old")
    (tmp_path / "new").mkdir()
    (tmp_path / "new" / "corpus.json").write_text("[]")
    snapshot.replace_dir(str(tmp_path / "new"), str(tmp_path / "live"))
    assert sorted(os.listdir(tmp_path / "live")) == ["corpus.json"]
    assert sorted(os.listdir(tmp_path)) == ["live"]


# ------------------------------------------------------------------------------
# 7.9 (a) sync_data
# ------------------------------------------------------------------------------
def make_snapshot_dir(root, generated_at):
    (root / "data" / "vectorstore").mkdir(parents=True)
    (root / "data" / "vectorstore" / "corpus.json").write_text("[]", encoding="utf-8")
    (root / "data" / "metadata.json").write_text(
        json.dumps({"generated_at": generated_at, "scrape_date": "2030-01-02", "run_id": "7"}), encoding="utf-8"
    )


def test_sync_data_installs_and_is_idempotent(tmp_path, monkeypatch, capsys):
    sync_data = load_script("sync_data")
    app_dir, artifact = tmp_path / "app", tmp_path / "artifact"
    (app_dir / "data" / "vectorstore").mkdir(parents=True)
    (app_dir / "data" / "vectorstore" / "stale.txt").write_text("x")
    make_snapshot_dir(artifact, "g2")
    monkeypatch.chdir(app_dir)

    assert sync_data.main(["--from-dir", str(artifact)]) == 0
    assert os.listdir("data/vectorstore") == ["corpus.json"]
    assert snapshot.read_metadata("data/metadata.json")["generated_at"] == "g2"
    assert (artifact / "data" / "metadata.json").exists()  # caller's directory untouched
    assert not [d for d in os.listdir("data") if d.startswith(".sync-")]

    assert sync_data.main(["--from-dir", str(artifact)]) == 0
    assert "Already up to date" in capsys.readouterr().out


# ------------------------------------------------------------------------------
# 7.8 publish guard and 7.10 alerting
# ------------------------------------------------------------------------------
def test_publish_requires_passing_marker_for_same_build(tmp_path):
    publish = load_script("publish_snapshot")
    marker = tmp_path / "marker.json"
    build = {"generated_at": "2026-11-21T10:05:00+05:30"}

    with pytest.raises(SystemExit, match="no validation marker"):
        publish.check_marker(str(marker), build)
    marker.write_text(json.dumps({"passed": False, "generated_at": build["generated_at"]}))
    with pytest.raises(SystemExit, match="failed"):
        publish.check_marker(str(marker), build)
    marker.write_text(json.dumps({"passed": True, "generated_at": "an older build"}))
    with pytest.raises(SystemExit, match="different build"):
        publish.check_marker(str(marker), build)
    marker.write_text(json.dumps({"passed": True, "generated_at": build["generated_at"]}))
    publish.check_marker(str(marker), build)


def test_report_failure_names_the_failing_stage():
    report = load_script("report_failure")
    steps = {"setup": {"outcome": "success"}, "ingest": {"outcome": "success"}, "validate": {"outcome": "failure"}}
    assert report.failing_stage(json.dumps(steps)) == "Validation gate"
    assert report.failing_stage("") == "Unknown step (see the run log)"
